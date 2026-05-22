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
            "num_predict": 2000, # cap output length
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

The prompt is the highest-leverage code in this project. It lives in `app/prompts/analyze_system.txt`, loaded by `app/analyze.py` and `scripts/analyze_test.py`.

### System prompt

The full system prompt — role framing, the three focus areas (lexical gaps,
Indonesian-isms, content feedback), the hard rules, and the worked examples — is
**not reproduced here**, to avoid drift. It lives in one canonical place:
**`app/prompts/analyze_system.txt`**, loaded by both `app/analyze.py` and
`scripts/analyze_test.py`. Read that file for the exact wording.

It instructs the model to return JSON in exactly this shape:

```json
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

After parsing, validate against the `Analysis` Pydantic model in `app/analyze.py` — the canonical schema (`Gap`, `ContentNote`, `Analysis`), which mirrors the JSON shape above (`content_feedback` defaults to an empty list).

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
