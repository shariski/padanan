# Local LLM Setup

How the LLM analysis half of Padanan works. The complement to [`audio-pipeline.md`](audio-pipeline.md).

## Why local, why MLX, why Qwen

The developer is self-hosting the LLM on purpose. Two reasons:

1. **Learning.** Running a local LLM stack is part of the project goal, not just a cost decision.
2. **Privacy.** Speaking practice recordings and transcripts stay on the developer's machine.

The trade-off is honest: a quantized ~9B local model produces flatter, less nuanced feedback than a frontier model would. Accepted.

**Runtime: MLX (`mlx_lm.server`).**

MLX is Apple's array framework; `mlx-lm` serves models on the Apple Silicon GPU (Metal) and exposes an **OpenAI-compatible** HTTP API at `localhost:8080` (`/v1/chat/completions`). The project originally ran on Ollama (a `llama.cpp` wrapper on `:11434`); it was swapped for MLX on 2026-06-15 to run natively on the Mac's GPU. Because `mlx_lm.server` speaks the OpenAI dialect, only the app's HTTP layer changed — the system prompt, schema, and retry logic were untouched.

**Model: Qwen3.5 9B, 6-bit MLX quantization (`mlx-community/Qwen3.5-9B-6bit`).**

- A 9B at 6-bit is ~7GB — heavier than the old 7B Q4 (~5GB), but still fits alongside Whisper (~1.5GB) and the OS on 16GB.
- Qwen's training set has stronger coverage of Asian-language content than Llama, which gives it a better shot at recognizing subtle Indonesian-language patterns leaking into English. This is an educated bet, not a benchmark — verify during dogfooding.
- Instruction-following at 9B is good enough for structured JSON output if the prompt is tight.

Swapping models is a one-line config change (`LLM_MODEL` in `app/analyze.py`): serve a different MLX model and point at it. If 9B quality is insufficient, try a larger MLX quant/model.

## Setup

```bash
# MLX lives in its own venv (~/.venvs/mlx). Install mlx-lm there:
pip install mlx-lm

# Serve the model (OpenAI-compatible API on :8080)
mlx_lm.server --model mlx-community/Qwen3.5-9B-6bit

# Sanity check (OpenAI-style chat completion)
curl -s http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mlx-community/Qwen3.5-9B-6bit","messages":[{"role":"user","content":"Reply with just the word OK."}],"max_tokens":10}'
```

Once `mlx_lm.server` is running, it exposes `http://localhost:8080`. Treat it as an always-on local service. (The first JSON-mode request after start can be slow or drop once — grammar/warmup — then it's fast.)

## API surface used by the app

Only the `/v1/chat/completions` endpoint (OpenAI-compatible). No streaming in MVP. Example:

```python
import httpx
import json

LLM_URL = "http://localhost:8080/v1/chat/completions"
LLM_MODEL = "mlx-community/Qwen3.5-9B-6bit"

async def analyze(transcript: str, prompt_text: str) -> dict:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(prompt_text, transcript)},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},  # OpenAI JSON mode: forces JSON-shaped output
        "temperature": 0.3,  # low for stable JSON, high enough for creative upgrades
        "max_tokens": 2000,  # cap output length
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(LLM_URL, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)
```

Notes:

- `response_format: {"type": "json_object"}` is the OpenAI-style JSON mode (supported by `mlx_lm.server`) that forces the model to emit valid JSON. It does not guarantee the schema is correct — only that the output parses. The schema is enforced by validation after parsing.
- 120-second timeout is generous. A short transcript through the real `analyze()` measured ~44s on Qwen3.5-9B-6bit (2026-06-15); longer clips will be slower. To be measured properly.
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
2. Run each through the analysis prompt with the local model.
3. For each output, judge:
   - Is the upgraded version actually an upgrade, or generic?
   - Are the lexical gaps real, or padded?
   - Is the overall_note pointed, or boilerplate?
4. Document in `docs/dogfooding.md`.

**Decision gate:** if at least 2 of 3 outputs are clearly useful, proceed with the current model. If not, try a larger MLX model and re-test. If that still isn't useful, the design needs revisiting before more code is written.

## Performance (first measurement 2026-06-15, MLX Qwen3.5-9B-6bit on Apple Silicon GPU)

- A real `analyze()` round-trip on a short (~55-word) transcript: **~44s** end-to-end — includes prefilling the long system prompt plus up to 2000 output tokens.
- The **first** JSON-mode request after `mlx_lm.server` starts can be slow or drop the connection once (grammar/warmup), then settles to ~1s for small calls.
- The app does **not** retry on connection errors — only on malformed JSON — so a cold-start flake means one failed analysis; just resubmit.
- A 90-second transcript yields ~250 input words → ~325 input tokens; output (JSON with upgraded version + gaps) is roughly 400–700 tokens. Longer clips will be slower — measure and update.

## What does not go in the LLM layer

- No streaming output to the UI (MVP shows "Analyzing…" then the full result)
- No multi-turn conversation (one request per session analysis)
- No tool use, no function calling, no agentic loops
- No RAG, no vector database, no embeddings — this is a single-prompt task
- No fine-tuning, no LoRA. If quality is bad, switch model or fix the prompt, do not train.
- No fallback to a cloud API. If the MLX server isn't running, the analysis fails — that's a feature, the developer chose self-hosted.

If any of the above start to look necessary, that's a design conversation, not a code change.
