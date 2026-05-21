"""Phase 2 LLM analysis sanity check.

Sends an interview prompt + a transcript to Qwen 7B via Ollama using the system
prompt from docs/local-llm-setup.md, validates the JSON output against the
Analysis schema, and prints the result. Retries once on schema-validation
failure, then fails loudly (no silent fallback).

The point (docs/plan.md Phase 2, docs/local-llm-setup.md "Quality sanity check"):
judge whether the local 7B model produces *useful* feedback — a real upgrade,
real gaps, a pointed overall_note — before any UI is built. This is a decision
gate: if it isn't useful, swap to Qwen 14B or rework the prompt first.

The system prompt, user template, schema, and request options here mirror what
will go into app/analyze.py, so this script doubles as the prompt's first test.

Usage:
    uv run python scripts/analyze_test.py \\
        --prompt "Explain what an API is and why it matters in backend systems." \\
        --transcript-file data/recordings/clip1.txt
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b-instruct-q4_K_M"

# Tightened from the base prompt in docs/local-llm-setup.md (Phase 2 dogfooding):
# added banned-phrase lists, a gap-granularity rule, a discourse-marker carve-out for
# indonesian_isms, and GOOD/BAD few-shot exemplars — to suppress the anti-patterns from
# docs/feedback-loop.md that Qwen 7B produced on the first run. The braces in the schema
# block are literal (plain string, not an f-string), so they pass through as-is.
SYSTEM_PROMPT = """\
You are an English language coach for senior software engineers. Your job is to help
a non-native English speaker — specifically, an Indonesian senior engineer
preparing for technical interviews at global remote companies — improve the LEXICAL
PRECISION of their spoken English.

The speaker is at B2-upper level. Their grammar is acceptable and their accent is
intelligible. Do NOT correct grammar except in cases where it materially obscures
meaning. Do NOT comment on accent or pronunciation — you cannot hear the recording,
only the transcript.

Your focus is twofold:

1. LEXICAL GAPS: Places where the speaker used a vague or weak word/phrase, and a
   more precise word from the senior-IC technical or business register would have
   served better. Example: "make it faster" → "reduce p99 latency". You are looking
   for the kind of word that an experienced engineer would reach for in the same
   sentence.

2. INDONESIAN-ISMS: Subtle patterns where Indonesian language structure leaked into
   English. Examples include: pluralizing non-count nouns ("informations",
   "feedbacks"), dropping the subject in a way that reads as ambiguous, direct
   translations of Indonesian discourse markers ("how if we..." for "what if
   we..."). These are RARE at B2 upper. Do not invent them. If there are none,
   return an empty list.

You will also produce an UPGRADED VERSION of the answer: the same content and
reasoning, but with senior-IC vocabulary and natural discourse markers. The
upgraded version should be recognizably the same answer, not a different answer.

HARD RULES — these are the difference between useful and useless output:

1. lexical_gaps granularity: each "spoken" and "suggested" is a SHORT phrase — a few
   words, not a whole sentence. A gap is one word/phrase the speaker could have swapped,
   not a paraphrase of a clause. Whole-sentence rewrites belong in upgraded_version, NEVER
   in lexical_gaps.

2. Suggest only swaps that change PRECISION or REGISTER. Never cosmetic swaps. Every
   "reason" must name a CONCRETE EFFECT of the swap: what the suggested word SIGNALS, what
   ambiguity it removes, or what follow-up question it invites. Self-test: if your reason
   would make sense for almost ANY swap — "more precise", "more concise", "more
   professional", "clearer", "sounds better", "uses technical terminology", "more
   natural" — it is wrong. Delete it and state the specific effect instead. (Good: "names
   which dimension of speed, signaling systems thinking." Bad: "more precise.")

3. indonesian_isms are RARE and specific to first-language (Indonesian) interference
   (e.g. pluralizing non-count nouns like "informations"; "how if we..." for "what if
   we..."). Casual discourse markers ("so", "okay", "right", "well") and ordinary
   disfluency, rambling, or wordiness are NOT Indonesian-isms — those belong in
   upgraded_version, never here. The most common correct value of this field is an empty
   list []. Only add an entry if you can name the specific Indonesian pattern. Do not pad.

4. overall_note is ONE pointed, answer-specific observation the speaker can act on.
   BANNED — never include praise or encouragement: "Good answer", "Great job", "Well
   done", "Keep up the good work", "Keep practicing", "nice work". If the answer is
   already at senior-IC register, say that plainly and return few or zero gaps.

5. If you cannot find at least three MEANINGFUL gaps, return fewer. Never pad the list.

The examples below show the FORM and quality bar ONLY. Never copy their specific words,
phrases, or domain into your output — derive everything from the speaker's actual answer.

GOOD lexical_gap (form):
  { "spoken": "make it faster", "suggested": "reduce p99 latency",
    "reason": "names which dimension of speed, signaling systems thinking" }
GOOD overall_note (form — pointed at THIS answer's specific weakness):
  "The structure is sound, but the answer describes each mechanism in general terms and
  never names the specific algorithm or data structure — that is the single change that
  would lift it to senior-IC depth."

BAD lexical_gap — NEVER produce this (cosmetic swap, contentless reason):
  { "spoken": "we need a service", "suggested": "we require a service",
    "reason": "more professional" }
BAD overall_note — NEVER produce this (empty praise, generic exhortation):
  "Good answer! Keep practicing and use more technical vocabulary."

Return your response as JSON with exactly this shape:

{
  "transcript_cleaned": string,
  "upgraded_version": string,
  "lexical_gaps": [
    { "spoken": string, "suggested": string, "reason": string }
  ],
  "indonesian_isms": [
    { "spoken": string, "suggested": string, "reason": string }
  ],
  "overall_note": string
}"""

RETRY_REMINDER = (
    "Your previous response did not match the required JSON schema. Respond again "
    "with ONLY valid JSON matching exactly the schema specified in the system "
    "prompt. No prose before or after the JSON."
)


class Gap(BaseModel):
    spoken: str
    suggested: str
    reason: str


class Analysis(BaseModel):
    transcript_cleaned: str
    upgraded_version: str
    lexical_gaps: list[Gap]
    indonesian_isms: list[Gap]
    overall_note: str


def user_prompt(prompt_text: str, transcript: str) -> str:
    return (
        f"INTERVIEW PROMPT:\n{prompt_text}\n\n"
        f"SPEAKER'S ANSWER (transcript):\n{transcript}\n\n"
        "Produce the analysis JSON."
    )


def call_ollama(messages: list[dict]) -> tuple[str, dict]:
    """One /api/chat round-trip. Returns (content, raw_response_json)."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 1500},
    }
    with httpx.Client(timeout=120) as client:
        r = client.post(OLLAMA_URL, json=payload)
        r.raise_for_status()
        data = r.json()
    return data["message"]["content"], data


def analyze(prompt_text: str, transcript: str) -> tuple[Analysis, int, float]:
    """Run analysis with one retry on schema failure.

    Returns (analysis, attempts, latency_seconds). Raises on final failure.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(prompt_text, transcript)},
    ]

    t0 = time.perf_counter()
    for attempt in (1, 2):
        content, _ = call_ollama(messages)
        try:
            return Analysis.model_validate_json(content), attempt, time.perf_counter() - t0
        except (ValidationError, json.JSONDecodeError) as e:
            if attempt == 2:
                raise
            print(f"[attempt 1 failed schema validation: {type(e).__name__}; retrying once]\n")
            # Append the bad reply + a strict reminder, per docs/local-llm-setup.md.
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": RETRY_REMINDER})

    raise RuntimeError("unreachable")  # loop either returns or raises


def render(analysis: Analysis) -> None:
    print("--- TRANSCRIPT (cleaned) ---")
    print(analysis.transcript_cleaned)
    print("\n--- UPGRADED VERSION ---")
    print(analysis.upgraded_version)
    print(f"\n--- LEXICAL GAPS ({len(analysis.lexical_gaps)}) ---")
    for i, g in enumerate(analysis.lexical_gaps, 1):
        print(f'{i}. "{g.spoken}" → "{g.suggested}"\n   {g.reason}')
    if analysis.indonesian_isms:
        print(f"\n--- INDONESIAN-ISMS ({len(analysis.indonesian_isms)}) ---")
        for i, g in enumerate(analysis.indonesian_isms, 1):
            print(f'{i}. "{g.spoken}" → "{g.suggested}"\n   {g.reason}')
    else:
        print("\n--- INDONESIAN-ISMS --- (none)")
    print("\n--- OVERALL NOTE ---")
    print(analysis.overall_note)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 LLM analysis sanity check.")
    parser.add_argument("--prompt", required=True, help="the interview prompt being answered")
    parser.add_argument(
        "--transcript-file",
        type=Path,
        required=True,
        help="path to a .txt file containing the transcript",
    )
    args = parser.parse_args()

    if not args.transcript_file.is_file():
        sys.exit(f"Transcript file not found: {args.transcript_file}")
    transcript = args.transcript_file.read_text().strip()

    print(f"Model: {MODEL}")
    print(f"Prompt: {args.prompt}\n")
    try:
        analysis, attempts, latency = analyze(args.prompt, transcript)
    except (ValidationError, json.JSONDecodeError) as e:
        sys.exit(f"\nANALYSIS FAILED — model returned malformed output after retry:\n{e}")
    except httpx.HTTPError as e:
        sys.exit(f"\nOllama request failed (is the service running?): {e}")

    print(f"[ok in {latency:.1f}s, {attempts} attempt(s), schema valid]\n")
    render(analysis)


if __name__ == "__main__":
    main()
