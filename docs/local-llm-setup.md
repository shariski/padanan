# Local LLM Setup

How the LLM analysis half of Padanan works. The complement to [`audio-pipeline.md`](audio-pipeline.md).

## Why local, why Ollama, why Qwen 2.5

The developer is self-hosting the LLM on purpose. Two reasons:

1. **Learning.** Running a local LLM stack is part of the project goal, not just a cost decision.
2. **Privacy.** Speaking practice recordings and transcripts stay on the developer's machine.

The trade-off is honest: a 7B local model produces flatter, less nuanced feedback than a frontier model would. Accepted.

**Runtime: Ollama.**

Ollama wraps `llama.cpp` and exposes an HTTP API at `localhost:11434`. It is the fastest way to a working setup. The developer plans to explore raw `llama.cpp` in a separate learning track later. For week one, Ollama is the right tool. If the temptation to switch to LM Studio or raw `llama.cpp` mid-week appears, defer — pick one runtime and ship.

**Model: Qwen 2.5 7B Instruct, Q4_K_M quantization.**

- Fits comfortably (~5GB) alongside Whisper (~1.5GB) and the OS on M4 16GB.
- Qwen 2.5's training set has stronger coverage of Asian-language content than Llama 3.1, which gives it a better shot at recognizing subtle Indonesian-language patterns leaking into English. This is an educated bet, not a benchmark — verify during dogfooding.
- Instruction-following at 7B is good enough for structured JSON output if the prompt is tight.

Backup model if quality is insufficient: **Qwen 2.5 14B Instruct Q4_K_M** (~8.5GB). Tight on 16GB but viable. Swap is a one-line config change.

## Setup

```bash
# Install Ollama (macOS):
brew install ollama
# Or download from https://ollama.com

# Start the daemon
ollama serve

# Pull the model (in another terminal)
ollama pull qwen2.5:7b-instruct-q4_K_M

# Sanity check
ollama run qwen2.5:7b-instruct-q4_K_M "Reply with just the word OK."
```

Once `ollama serve` is running, it exposes `http://localhost:11434`. Treat it as an always-on local service.

## API surface used by the app

Only the `/api/chat` endpoint. No streaming in MVP. Example:

```python
import httpx
import json

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b-instruct-q4_K_M"

async def analyze(transcript: str, prompt_text: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(prompt_text, transcript)},
        ],
        "stream": False,
        "format": "json",        # Ollama-side JSON mode: forces JSON-shaped output
        "options": {
            "temperature": 0.3,  # low for stable JSON, high enough for creative upgrades
            "num_predict": 1500, # cap output length
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(OLLAMA_URL, json=payload)
        r.raise_for_status()
        content = r.json()["message"]["content"]
    return json.loads(content)
```

Notes:

- `"format": "json"` is an Ollama feature that forces the model to emit valid JSON. It does not guarantee the schema is correct — only that the output parses. The schema is enforced by validation after parsing.
- 120-second timeout is generous. Typical analysis of a 90-second transcript with Qwen 7B Q4 on M4 should be 10–25 seconds. To be measured.
- `temperature=0.3` is a starting point. If output feels too rigid or generic, raise to 0.5. If it produces invalid JSON or hallucinates structure, lower to 0.2.

## The prompt

The prompt is the highest-leverage code in this project. It lives in `app/analyze.py` as a string constant (or in `app/prompts/analyze_system.txt` if it grows past ~50 lines).

### System prompt

> Tightened during Phase 2 dogfooding (2026-05-21) to suppress the `feedback-loop.md`
> anti-patterns the base prompt produced on Qwen 7B — see `dogfooding.md` for the
> before/after. The version below is the validated one, mirrored in
> `scripts/analyze_test.py` until `app/analyze.py` exists. (It is now ~60 lines, so per
> the guidance above it belongs in `app/prompts/analyze_system.txt` when the app is built.)

```
You are an English language coach for senior software engineers. Your job is to help
a non-native English speaker — specifically, an Indonesian senior engineer
preparing for technical interviews at global remote companies — improve the LEXICAL
PRECISION of their spoken English.

The speaker is at B2-upper level. Their grammar is acceptable and their accent is
intelligible. Do NOT correct grammar except in cases where it materially obscures
meaning. Do NOT comment on accent or pronunciation — you cannot hear the recording,
only the transcript.

Your focus is threefold:

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

3. CONTENT FEEDBACK: Unlike the two above, this judges WHAT the speaker said, not how
   they said it. Read the interview prompt and assess the substance of the answer.
   Each item has a "kind":
   - "missing": an important point a strong senior answer to THIS prompt would cover
     that the speaker did not raise at all.
   - "weak": a point the speaker did raise but left thin, hand-wavy, or unjustified
     where a senior IC would go one level deeper.
   - "check": a specific claim the speaker made that looks technically questionable.
     Frame it as something to VERIFY, never as a verdict — you may be wrong, and a
     confident wrong "correction" is worse than saying nothing.
   This is separate from the upgraded version, which still preserves the speaker's
   content. Content fixes live ONLY here, never by silently rewriting their ideas.

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

6. content_feedback is the ONE place you judge substance. Prioritize "missing" and
   "weak" — coverage and depth are the high-value, lower-risk feedback. Add "check"
   items only when you are reasonably confident a claim is off, and word them as
   "Verify whether…", never "this is wrong". Every "note" must be specific to THIS
   answer and THIS prompt — name the actual point, never generic advice like "add more
   detail" or "consider scalability". Do NOT restate lexical gaps here; this is about
   ideas, not words. Return 2-5 items when warranted, fewer or none if the answer is
   genuinely complete and sound. Never pad.

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

GOOD content_feedback (form — specific to the answer and the prompt):
  { "kind": "missing", "note": "You never addressed how slugs stay unique under concurrent
    writes — a senior answer names the ID-generation or collision strategy." }
  { "kind": "check", "note": "Verify whether a single auto-increment counter holds at your
    stated write rate; at high QPS that counter is often the bottleneck." }
BAD content_feedback — NEVER produce this (generic, not answer-specific):
  { "kind": "weak", "note": "Add more detail and consider scalability and edge cases." }

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
  "content_feedback": [
    { "kind": "missing" | "weak" | "check", "note": string }
  ],
  "overall_note": string
}
```

### User prompt template

```
INTERVIEW PROMPT:
{prompt_text}

SPEAKER'S ANSWER (transcript):
{transcript}

Produce the analysis JSON.
```

## JSON validation

After parsing, validate. Use `pydantic` (already a FastAPI dep) for the schema:

```python
from pydantic import BaseModel
from typing import List

class Gap(BaseModel):
    spoken: str
    suggested: str
    reason: str

class ContentNote(BaseModel):
    kind: str  # missing | weak | check
    note: str

class Analysis(BaseModel):
    transcript_cleaned: str
    upgraded_version: str
    lexical_gaps: List[Gap]
    indonesian_isms: List[Gap]
    content_feedback: List[ContentNote] = []
    overall_note: str
```

If validation fails, retry **once** with a strict re-prompt appended to the conversation:

```
Your previous response did not match the required JSON schema. Respond again with
ONLY valid JSON matching exactly the schema specified in the system prompt. No
prose before or after the JSON.
```

If the second attempt also fails, surface the error to the user (the results screen shows "Analysis failed — model returned malformed output. Try again."). Do not silently fall back to displaying raw text. The schema is the contract; broken schema is a real failure mode worth seeing.

## Quality sanity check

Before building UI, after Whisper is working:

1. Use 3 transcripts from the Whisper sanity check (`audio-pipeline.md`).
2. Run each through the analysis prompt with Qwen 7B Q4.
3. For each output, judge:
   - Is the upgraded version actually an upgrade, or generic?
   - Are the lexical gaps real, or padded?
   - Is the overall_note pointed, or boilerplate?
4. Document in `docs/dogfooding.md`.

**Decision gate:** if at least 2 of 3 outputs are clearly useful, proceed with Qwen 7B. If not, pull Qwen 14B and re-test. If 14B still isn't useful, the design needs revisiting before more code is written.

## Performance expectations (to be measured, not assumed)

These are educated guesses on M4 16GB, **not benchmarks**:

- Qwen 2.5 7B Q4 inference: ~15–30 tokens/second
- Qwen 2.5 14B Q4 inference: ~8–15 tokens/second
- A 90-second transcript yields ~250 input words → ~325 input tokens
- The analysis output (JSON with upgraded version + gaps) is roughly 400–700 tokens
- Total request latency for 7B: ~10–25 seconds
- Total request latency for 14B: ~25–60 seconds

Measure on day one and update this section with real numbers.

## What does not go in the LLM layer

- No streaming output to the UI (MVP shows "Analyzing…" then the full result)
- No multi-turn conversation (one request per session analysis)
- No tool use, no function calling, no agentic loops
- No RAG, no vector database, no embeddings — this is a single-prompt task
- No fine-tuning, no LoRA. If quality is bad, switch model or fix the prompt, do not train.
- No fallback to a cloud API. If Ollama isn't running, the analysis fails — that's a feature, the developer chose self-hosted.

If any of the above start to look necessary, that's a design conversation, not a code change.
