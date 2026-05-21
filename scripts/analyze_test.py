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

# The system prompt — the single source of truth — lives in
# app/prompts/analyze_system.txt (also loaded by app/analyze.py). Loading it here
# keeps this sanity script testing the exact prompt the app ships.
SYSTEM_PROMPT = (
    Path(__file__).parent.parent / "app" / "prompts" / "analyze_system.txt"
).read_text()

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
