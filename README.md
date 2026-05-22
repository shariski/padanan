# Padanan

**Personal English speaking coach for Indonesian senior engineers prepping for global remote interviews.**

The name *padanan* is Indonesian for "equivalent" or "match" — the word you reach for when you say "lupa padanan-nya apa ya" (forgot what the equivalent is). That's the pain point this app addresses.

Padanan answers one need: when speaking English in interviews, *the right word doesn't come*. The grammar is fine. The accent is fine. But mid-sentence the speaker pauses, settles for a vague word ("make it faster"), and loses momentum where a more precise word ("reduce tail latency") would have kept the answer crisp.

The app records a short spoken answer to a technical or behavioral prompt, transcribes it locally, and uses a local LLM to produce two outputs side by side:

1. **Your answer**, cleaned up from the transcript
2. **A senior-IC native upgrade** of the same content — same idea, sharper vocabulary, better discourse markers — so the gap is visible in context

Plus a short list of **lexical gaps** (places where a more precise word would have served the answer better) and a separate **"content to check"** list — points a strong senior answer would cover that you missed, areas you left thin, and claims worth verifying.

The lexical upgrade is the core; the content notes are framed as prompts for your own judgment, not authoritative corrections — a local 7B confidently grading correctness is the one thing it does worst, so it flags rather than declares.

## What it deliberately does not do

- No pronunciation analysis. Phoneme-level acoustic analysis is hard, requires specialized tooling, and is not the main pain point at B2 upper level.
- No filler / pause / disfluency detection in MVP. Whisper's behavior with fillers is inconsistent and verifying this needs experimentation budget we don't have in week one.
- No personal vocabulary corpus, no spaced repetition, no cross-session pattern surfacing. These need data from many sessions and are deferred.
- No grammar drilling. Grammar is rank #2 in pain, and the comparative-output design surfaces grammar issues implicitly when the upgraded version differs.
- No mobile-native app, no menubar app, no notifications. Web only.
- No authoritative grading of technical correctness. The content-to-check notes flag points to verify and gaps to consider; they never declare your answer right or wrong, because a local 7B isn't reliable enough to be trusted as a verdict.

These are explicit scope decisions, not "coming soon."

## Stack

- **Frontend:** HTML + HTMX, served by FastAPI
- **Backend:** Python, FastAPI
- **Speech-to-text:** `faster-whisper` running locally (Whisper large-v3 or large-v3-turbo)
- **LLM:** Ollama serving Qwen 2.5 7B Instruct (Q4_K_M), with the option to upgrade to Qwen 2.5 14B if quality is insufficient
- **Runtime host:** Mac mini M4 16GB
- **Access:** localhost for dev, Tailscale for remote use (e.g. from iPhone Safari)
- **Recording:** browser `MediaRecorder` API → audio file POST → backend

No cloud APIs. No paid services. The Lenovo Legion is out of scope for week one.

## Status

MVP built and dogfooded on the Mac mini (Phases 0–10). The full loop works: record → transcribe (faster-whisper `large-v3-turbo`) → analyze (Qwen 2.5 7B via Ollama) → side-by-side results, with a session history. The app is reachable over Tailscale (binds `0.0.0.0`), but iPhone **recording** needs Tailscale HTTPS — `getUserMedia` requires a secure context, and the tailnet's HTTPS certs aren't enabled yet (see `audio-pipeline.md`). Latency is also marginally over the 45s target on 60s+ clips. See [`docs/plan.md`](docs/plan.md) for the task list, [`docs/dogfooding.md`](docs/dogfooding.md) for usage notes, and [`docs/risks.md`](docs/risks.md) for known unknowns.

Run it: `uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`, then open http://localhost:8000 (requires Ollama running with `qwen2.5:7b-instruct-q4_K_M` pulled).

## License

Personal project. No license granted.
