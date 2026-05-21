# Build Plan

A flat, checkbox-able task list. No days. No time estimates. Tasks are grouped into phases by **dependency**, not schedule — finish a phase before starting the next, because each phase's output is the next phase's input.

If a phase's sanity check fails, **stop and reassess** before continuing. The point of the sanity checks is to fail fast, not to be skipped.

---

## Phase 0 — Environment

- [ ] Install Ollama and start `ollama serve` as a launchd service or background process
- [ ] Pull `qwen2.5:7b-instruct-q4_K_M`
- [ ] Verify Ollama responds to a curl POST at `localhost:11434/api/chat`
- [ ] Install `ffmpeg` (`brew install ffmpeg`)
- [ ] Confirm Python 3.11+ is available
- [ ] Create project directory, `git init`, copy `.gitignore` (Python + macOS + `data/`)
- [ ] Set up `pyproject.toml` with `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `jinja2`, `faster-whisper`, `aiosqlite`, `ruff`
- [ ] Install Tailscale on the Mac mini and verify the device is reachable from the iPhone

## Phase 1 — Whisper sanity check

The point of this phase is to know whether transcription is good enough **before** building anything around it.

- [ ] Write a one-file script `scripts/whisper_test.py` that loads `large-v3-turbo` and transcribes a given file
- [ ] Record 3 test clips on the Mac mini (built-in or AirPods mic): 30s technical explanation, 60s STAR answer, 90s system design opening
- [ ] Transcribe each clip
- [ ] Read each transcript and rate: acceptable / minor issues / unacceptable
- [ ] Document results in `docs/dogfooding.md` (create the file)
- [ ] **Decision gate:** if any rating is "unacceptable", retry with `large-v3` (non-turbo). If still unacceptable, stop and reassess the project.

## Phase 2 — LLM sanity check

The point of this phase is to know whether Qwen 7B can produce useful feedback **before** building UI.

- [ ] Write `scripts/analyze_test.py` that takes a prompt + transcript and calls Ollama with the system prompt from `local-llm-setup.md`
- [ ] Run it against each of the 3 transcripts from Phase 1
- [ ] Validate each output against the pydantic `Analysis` schema
- [ ] For each output, judge: is the upgraded version a real upgrade? are the gaps real or padded? is the overall_note pointed?
- [ ] Append results to `docs/dogfooding.md`
- [ ] **Decision gate:** if fewer than 2 of 3 outputs are clearly useful, pull `qwen2.5:14b-instruct-q4_K_M`, swap the model name, re-run. If still not useful, stop and rework the prompt before building UI.

## Phase 3 — Backend skeleton

- [ ] Create `app/main.py` with a FastAPI app and a single `/` route returning a hello template
- [ ] Run `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` and confirm reachable from the Mac mini browser
- [ ] Confirm reachable from the iPhone via Tailscale hostname
- [ ] Add static file mount and serve `htmx.min.js` locally
- [ ] Add a `pages` Jinja2 template directory and a base layout

## Phase 4 — Prompt library

- [ ] Create `app/prompts/library.json` with the 13 prompts from `product-spec.md` §4
- [ ] Load the library at app startup
- [ ] Render the session-start screen with library + custom tabs
- [ ] Selecting a prompt navigates to the recording screen with the prompt rendered

## Phase 5 — Recording flow

- [ ] Recording screen template: prompt at top, big Record/Stop button, timer
- [ ] JS for `MediaRecorder` (vanilla, no framework): start, stop, collect chunks, POST blob to `/api/sessions`
- [ ] Backend route `POST /api/sessions` that creates a session row, saves the audio file to `data/recordings/<id>.<ext>`, returns the session id
- [ ] Confirm round-trip works on Mac mini Chrome and on iPhone Safari (via Tailscale, with the secure-context caveat from `audio-pipeline.md`)

## Phase 6 — Transcription wiring

- [ ] `app/transcribe.py` with a `WhisperModel` instance loaded at app startup
- [ ] Function `transcribe_session(session_id)` that reads the audio file, runs ffmpeg conversion to 16kHz mono WAV, calls `model.transcribe(...)`, stores transcript in the session row
- [ ] After `POST /api/sessions`, trigger transcription (synchronous in MVP — the request takes ~10 seconds, which is fine for one user)
- [ ] Return a 302 / HTMX redirect to the analyzing screen

## Phase 7 — Analysis wiring

- [ ] `app/analyze.py` with the system prompt as a constant, `Analysis` pydantic schema, `analyze(transcript, prompt_text)` async function calling Ollama
- [ ] JSON validation with one retry on schema failure (see `local-llm-setup.md`)
- [ ] After transcription, call `analyze()` and store the result JSON in `sessions.analysis_json`
- [ ] On schema-validation failure after retry, mark the session as failed and surface the error

## Phase 8 — Results screen

- [ ] Results template: prompt (collapsible), transcript, upgraded version (side-by-side or stacked responsively), lexical gaps list, indonesian-isms list (hidden if empty), overall note, Retry and New session buttons
- [ ] "Retry" button starts a new session with the same prompt
- [ ] "Play original recording" small button that uses the saved audio file

## Phase 9 — History

- [ ] `/history` route showing reverse-chronological session list
- [ ] Each row links to a `/sessions/<id>` view that renders the same results template

## Phase 10 — Polish and dogfood

- [ ] Real end-to-end run on Mac mini: pick library prompt → record 60s → see analysis
- [ ] Real end-to-end run on iPhone via Tailscale
- [ ] Three dogfooding sessions on real interview prep, with notes in `docs/dogfooding.md`
- [ ] Final pass on the prompt based on what dogfooding revealed
- [ ] Confirm acceptance criteria in `product-spec.md` §9 are all checked

---

## Stop conditions

Stop and reassess if:

- Phase 1 ends with "unacceptable" on `large-v3` — Whisper does not handle the developer's accent well enough, the whole approach needs rethinking
- Phase 2 ends with "fewer than 2 of 3 useful" on Qwen 14B — local LLM quality is the bottleneck, either the prompt needs major rework or the self-hosting decision needs revisiting
- Phase 5 hits insurmountable `MediaRecorder` / Tailscale / secure-context issues — fall back to Mac-only access (no remote) is acceptable, but the decision should be conscious

## Out of scope for this plan

If any of these come up during the build, do not do them, even if they seem small:

- Auth, accounts, multi-user
- Mobile-native app
- Streaming transcription, streaming LLM
- Pronunciation analysis
- Vocabulary corpus, SRS
- Filler / pause detection
- Cloud LLM fallback
- Tests beyond prompt-construction tests
- Docker, CI/CD
- Anything in `risks.md` marked "deferred"
