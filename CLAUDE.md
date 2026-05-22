# CLAUDE.md

Behavioral guidelines for Claude Code when working on **Padanan**.

This file merges two layers:

- **Part A** — universal LLM coding principles (from Andrej Karpathy's observations, via multica-ai/andrej-karpathy-skills)
- **Part B** — project-specific rules for Padanan (web-based English speaking coach, local Whisper + local LLM)

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks (typos, obvious one-liners), use judgment — not every change needs the full rigor.

---

# PART A — Universal Principles

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# PART B — Padanan Project Rules

## What this project is

A one-week, single-developer web app. Personal use only. The developer is a tech lead in Indonesia, native Bahasa Indonesia speaker, B2-upper English, prepping for senior IC remote interviews at global companies.

The point of the app is **lexical retrieval practice**: surface the gap between the words that come out and the words that *should* come out, so the developer can close that gap before real interviews.

The point is **not** to be a generic English tutor. It is not for grammar drilling, accent training, or vocabulary expansion in the abstract. Every feature must serve the specific loop: record answer → see comparative output → notice gap.

Lexical retrieval is still the core, but the app now also surfaces a **separate, hedged content-feedback dimension** (points a strong senior answer would cover that you missed, areas left thin, and claims worth verifying). This was added after dogfooding showed lexical-only feedback wasn't enough for interview prep. It is deliberately framed as *things to check, not authoritative corrections* — a local 7B confidently grading technical correctness is the riskiest thing it does, so content notes prompt the developer's own judgment rather than asserting truth.

## Audience: who runs this code

One person. The developer. Localhost or Tailscale. No multi-tenancy, no auth, no rate limiting, no observability stack, no Docker, no CI/CD.

If you find yourself reaching for any of the above, stop and ask.

## Stack constraints

- **Backend:** Python 3.11+, FastAPI, uvicorn.
- **Frontend:** HTML templates (Jinja2), HTMX for interactivity. **No React, no Vue, no SvelteKit, no build step.** If a feature seems to need a build step, the feature is wrong for this stack — push back.
- **Speech-to-text:** `faster-whisper` (CTranslate2-based). Not `openai-whisper` (slower) and not `whisper.cpp` (different API, lower priority for week one).
- **LLM:** Ollama HTTP API at `localhost:11434`. Default model: `qwen2.5:7b-instruct-q4_K_M`. The model name lives in a config constant — do not hardcode it in multiple places.
- **Storage:** SQLite via `sqlite3` stdlib or `aiosqlite`. No ORM. One file: `padanan.db`.
- **Audio in browser:** `MediaRecorder` API, format `audio/webm` or `audio/mp4` depending on browser. Backend converts to whatever Whisper needs.

## What goes in the repo

```
padanan/
├── README.md
├── CLAUDE.md               (this file)
├── docs/
│   ├── product-spec.md
│   ├── feedback-loop.md    (the core: what feedback looks like and why)
│   ├── audio-pipeline.md   (Whisper setup, known limitations)
│   ├── local-llm-setup.md  (Ollama, model choice, prompt structure)
│   ├── plan.md             (flat task list, checkbox-able)
│   └── risks.md            (known unknowns, deferred features)
├── app/
│   ├── main.py             (FastAPI app)
│   ├── routes.py
│   ├── transcribe.py       (Whisper wrapper)
│   ├── analyze.py          (Ollama wrapper + prompt construction)
│   ├── prompts/            (prompt library: system_design.json, behavioral.json, etc.)
│   ├── templates/          (Jinja2)
│   └── static/             (htmx.min.js, minimal CSS)
├── data/
│   ├── padanan.db
│   └── recordings/         (audio files, gitignored)
├── tests/
│   └── ...                 (only where it earns its keep — see below)
├── pyproject.toml
└── .gitignore
```

## Testing philosophy

This is a one-week personal app. **Do not write comprehensive test suites.** Write a test only when:

1. The logic is non-obvious enough that you can't verify it by inspection, OR
2. It's a regression you've already hit once, OR
3. It's the prompt construction layer — that earns tests because prompt changes are silent breakers.

No mocking the LLM in tests. No mocking Whisper. If you can't verify it by running the actual app against a real recording, the test isn't pulling its weight.

## What does NOT belong in this codebase

- User authentication. There is one user.
- Multi-language UI. The UI is in English. The transcripts and analysis are in English. Bahasa Indonesia appears only when the LLM is explaining an Indonesian-ism it detected.
- Real-time streaming transcription. The MVP is: record → stop → submit → wait → see result. Streaming is deferred.
- WebSocket. HTMX polling or simple POST is enough.
- Voice activity detection beyond what Whisper provides. No `silero-vad` integration for MVP.
- Pronunciation scoring. Out of scope.
- Filler / pause / disfluency detection. Deferred (see `risks.md`).
- A vocabulary corpus or SRS system. Deferred.

If a request seems to push toward any of the above, ask whether it's actually MVP scope before writing code.

## LLM prompt discipline

The single prompt that does "analyze the transcript and produce comparative output + lexical gaps" is the highest-leverage piece of code in this project. Treat it like production code:

- It lives in `app/analyze.py` (or `app/prompts/analyze.txt` loaded as a string — pick one and stick with it).
- It is structured (system prompt + user prompt with clear sections), not a single freeform blob.
- Changes to it are committed with a sample input/output pair in the commit message.
- The output is JSON with a known schema — do not free-form parse the model's reply.
- If the model returns malformed JSON, retry once with a stricter "respond with ONLY valid JSON" reminder, then fail loudly.

The prompt's job, specifically:

1. Take the transcript and the original prompt (the question being answered)
2. Identify Indonesian-isms (direct-translation artifacts) if any — at B2 upper they will be subtle
3. Identify lexical gaps — vague words where precise senior-IC vocabulary would serve better
4. Produce a "senior-IC native version" that preserves the speaker's content and reasoning but upgrades vocabulary and discourse markers
5. Surface content feedback — missing/weak/check notes on the answer's substance, kept separate from the lexical upgrade and framed as things to verify, not authoritative corrections
6. Return all of that as JSON

The full prompt design lives in `docs/feedback-loop.md`. Read it before touching `analyze.py`.

## Model choice and quality expectations

Default: **Qwen 2.5 7B Instruct Q4_K_M**. Chosen for:

- Fits in 16GB unified memory with headroom for Whisper + FastAPI + browser
- Qwen training data has stronger Asian-language coverage than Llama, giving it a better shot at recognizing Indonesian-isms
- Instruction-following at 7B is acceptable for structured-output tasks if the prompt is tight

**Be honest about quality.** A 7B local model will produce flatter, less nuanced output than Claude Sonnet would. The "senior-IC native version" will sometimes sound generic or miss subtle phrasing improvements. This is an accepted trade-off — the developer chose self-hosting to learn local LLM serving, not because it produces the best feedback.

If quality is clearly insufficient after MVP, the next step is upgrading to **Qwen 2.5 14B Instruct Q4_K_M** (~8.5GB, tight but viable on M4 16GB). Do not propose switching to a cloud API as the first lever.

## Whisper choice and known limitations

`faster-whisper` with `large-v3` (or `large-v3-turbo` if it's faster on M4 — to be tested). On Apple Silicon, this runs via CTranslate2 with CPU or CoreML — **GPU acceleration via Metal is not directly supported by faster-whisper**. Performance is acceptable for short clips (under 90 seconds) which is the target use case.

Known limitations the developer needs to be aware of, and Claude Code should not silently work around:

- Whisper smooths fillers ("um", "uh", false starts) inconsistently. The MVP does not depend on detecting these. Do not add post-processing to recover them.
- Whisper has not been benchmarked specifically on Indonesian-accented English. Transcription quality is a known risk. The MVP plan includes a sanity-check task to evaluate this early.
- Word-level timestamps are available but not used in MVP. Don't enable them by default; they slow inference.

## Networking and access

- Dev: `localhost:8000`
- Remote (e.g. iPhone Safari while away from desk): Tailscale. The FastAPI server binds to `0.0.0.0:8000`, Tailscale handles the rest. No HTTPS in MVP — Tailscale-internal traffic is fine for a one-person personal app.
- Microphone access in browser **requires a secure context**. `localhost` is treated as secure. Over Tailscale, the Tailscale hostname is also fine via Tailscale's MagicDNS + HTTPS certificates if the developer enables them. If `MediaRecorder` errors on remote access, this is the most likely cause — flag it, don't paper over it.

## Code style

- Type hints everywhere they're free (function signatures, return types). Not religiously elsewhere.
- `ruff` for linting and formatting. No `black` + `isort` + `flake8` zoo.
- No `mypy --strict`. The project is too small to earn it.
- Imports: stdlib, third-party, local — three groups, blank line between.
- Async where FastAPI expects it (routes, I/O). Sync where it's simpler.

## Definition of done for MVP

The MVP is done when the developer can:

1. Open the web app in a browser (Mac mini local or iPhone via Tailscale)
2. Pick a prompt from the library (or paste a custom one)
3. Tap record, speak for 60–90 seconds, tap stop
4. Within ~30 seconds, see:
   - The transcript
   - The "senior-IC native upgrade" rendered side-by-side or above/below the transcript
   - A list of 3–8 lexical gaps with the speaker's word, the suggested word, and a one-sentence reason
5. Repeat as many times as they want without restarting anything

Anything beyond this is post-MVP. Anything that does not directly serve this loop is post-MVP.

## When in doubt

Read `docs/feedback-loop.md`. That document is the source of truth for *why* the app exists. If a proposed change does not make the feedback loop tighter or the comparative output more useful, it's probably out of scope.
