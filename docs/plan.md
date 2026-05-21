# Build Plan

A flat, checkbox-able task list. No days. No time estimates. Tasks are grouped into phases by **dependency**, not schedule — finish a phase before starting the next, because each phase's output is the next phase's input.

If a phase's sanity check fails, **stop and reassess** before continuing. The point of the sanity checks is to fail fast, not to be skipped.

---

## Phase 0 — Environment

- [x] Install Ollama and start `ollama serve` as a launchd service or background process
- [x] Pull `qwen2.5:7b-instruct-q4_K_M`
- [x] Verify Ollama responds to a curl POST at `localhost:11434/api/chat`
- [x] Install `ffmpeg` (`brew install ffmpeg`)
- [x] Confirm Python 3.11+ is available
- [x] Create project directory, `git init`, copy `.gitignore` (Python + macOS + `data/`)
- [x] Set up `pyproject.toml` with `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `jinja2`, `faster-whisper`, `aiosqlite`, `ruff`
- [ ] Install Tailscale on the Mac mini and verify the device is reachable from the iPhone _(deferred — localhost-only until Phase 5 remote recording)_

## Phase 1 — Whisper sanity check

The point of this phase is to know whether transcription is good enough **before** building anything around it.

- [x] Write a one-file script `scripts/whisper_test.py` that loads `large-v3-turbo` and transcribes a given file
- [x] Record 3 test clips on the Mac mini (built-in or AirPods mic): 30s technical explanation, 60s STAR answer, 90s system design opening _(1 of 3 recorded — 30s technical explanation; transcription clearly acceptable, developer chose not to record clips 2–3)_
- [x] Transcribe each clip _(clip 1)_
- [x] Read each transcript and rate: acceptable / minor issues / unacceptable _(clip 1: acceptable)_
- [x] Document results in `docs/dogfooding.md` (create the file)
- [x] **Decision gate:** if any rating is "unacceptable", retry with `large-v3` (non-turbo). If still unacceptable, stop and reassess the project. _(Passed on large-v3-turbo, RTF 0.30x.)_

## Phase 2 — LLM sanity check

The point of this phase is to know whether Qwen 7B can produce useful feedback **before** building UI.

- [x] Write `scripts/analyze_test.py` that takes a prompt + transcript and calls Ollama with the system prompt from `local-llm-setup.md`
- [x] Run it against each of the 3 transcripts from Phase 1 _(run against clip1 + clip2; clip1 too basic to judge gap quality, clip2 used as the real test)_
- [x] Validate each output against the pydantic `Analysis` schema _(schema-valid on the first attempt every run)_
- [x] For each output, judge: is the upgraded version a real upgrade? are the gaps real or padded? is the overall_note pointed?
- [x] Append results to `docs/dogfooding.md`
- [x] **Decision gate:** if fewer than 2 of 3 outputs are clearly useful, pull `qwen2.5:14b-instruct-q4_K_M`, swap the model name, re-run. If still not useful, stop and rework the prompt before building UI. _(Passed on 7B after tightening the prompt over 3 iterations; 14B not needed for MVP.)_

## Phase 3 — Backend skeleton

- [x] Create `app/main.py` with a FastAPI app and a single `/` route returning a hello template
- [x] Run `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` and confirm reachable from the Mac mini browser _(verified in-browser: page renders + HTMX swap works)_
- [ ] Confirm reachable from the iPhone via Tailscale hostname _(deferred with Tailscale — Phase 5)_
- [x] Add static file mount and serve `htmx.min.js` locally _(htmx 2.0.4, pinned)_
- [x] Add a `pages` Jinja2 template directory and a base layout _(used `app/templates/` per CLAUDE.md repo structure, not `pages/`; base.html + index.html)_

## Phase 4 — Prompt library

- [x] Create `app/prompts/library.json` with the 13 prompts from `product-spec.md` §4
- [x] Load the library at app startup _(loaded once at module import; id→prompt lookup)_
- [x] Render the session-start screen with library + custom tabs _(grouped list, all prompts visible, instead of the §3.1 category drill-down — simpler for 13 items)_
- [x] Selecting a prompt navigates to the recording screen with the prompt rendered _(library: GET /record/{id}; custom: POST /record; recording controls deferred to Phase 5)_

## Phase 5 — Recording flow

- [x] Recording screen template: prompt at top, big Record/Stop button, timer _(timer colors: black <90s, amber 90–120s, red >120s per §3.2)_
- [x] JS for `MediaRecorder` (vanilla, no framework): start, stop, collect chunks, POST blob to `/api/sessions` _(`app/static/recorder.js`; secure-context guard included)_
- [x] Backend route `POST /api/sessions` that creates a session row, saves the audio file to `data/recordings/<id>.<ext>`, returns the session id _(+ `app/db.py` with the `sessions` table; duration via ffprobe)_
- [x] Confirm round-trip works on Mac mini Chrome and on iPhone Safari (via Tailscale, with the secure-context caveat from `audio-pipeline.md`) _(live mic test passed in Mac Chrome — record → upload round-trip works; iPhone/Tailscale still deferred to when Tailscale is set up)_

## Phase 6 — Transcription wiring

- [x] `app/transcribe.py` with a `WhisperModel` instance loaded at app startup _(loaded in the lifespan via `load_model()`, not at import)_
- [x] Function `transcribe_session(session_id)` that reads the audio file, runs ffmpeg conversion to 16kHz mono WAV, calls `model.transcribe(...)`, stores transcript in the session row _(split into pure `transcribe_audio(path)` + `db.set_transcript`, orchestrated in the route — cleaner separation)_
- [x] After `POST /api/sessions`, trigger transcription (synchronous in MVP — the request takes ~10 seconds, which is fine for one user) _(via `asyncio.to_thread`; ~29s for a 130s clip)_
- [x] Return a 302 / HTMX redirect to the analyzing screen _(JSON `{redirect}` + JS navigation, since upload is fetch-based; lands on `GET /sessions/{id}`)_

## Phase 7 — Analysis wiring

- [x] `app/analyze.py` with the system prompt as a constant, `Analysis` pydantic schema, `analyze(transcript, prompt_text)` async function calling Ollama _(prompt in `app/prompts/analyze_system.txt`, the single source also used by `scripts/analyze_test.py`)_
- [x] JSON validation with one retry on schema failure (see `local-llm-setup.md`)
- [x] After transcription, call `analyze()` and store the result JSON in `sessions.analysis_json`
- [x] On schema-validation failure after retry, mark the session as failed and surface the error _(stored as `{"error": ...}`; results page shows "Analysis failed — try again"; also covers an unreachable Ollama)_

## Phase 8 — Results screen

- [x] Results template: prompt (collapsible), transcript, upgraded version (side-by-side or stacked responsively), lexical gaps list, indonesian-isms list (hidden if empty), overall note, Retry and New session buttons _(side-by-side via CSS grid ≥760px; collapsible via native `<details>`)_
- [x] "Retry" button starts a new session with the same prompt _(GET `/sessions/{id}/retry` reuses the prompt + source)_
- [x] "Play original recording" small button that uses the saved audio file _(native `<audio>` served by GET `/sessions/{id}/audio`)_

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
