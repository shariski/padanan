# Dogfooding Log

Results from the sanity-check gates and ongoing real-use notes. Referenced by
`plan.md` (Phases 1, 2, 10), `product-spec.md` §9, `audio-pipeline.md`,
`local-llm-setup.md`, and `feedback-loop.md`.

The two sanity checks below are **decision gates** — if a gate fails, stop and
reassess before building further (see `plan.md` stop conditions).

---

## Phase 1 — Whisper accuracy sanity check

Setup: `large-v3-turbo`, CPU, int8, via `scripts/whisper_test.py`.
Hardware: Mac mini M4 16GB. &nbsp; Mic: _____ (built-in / AirPods). &nbsp; Date: _____

Rate each transcript: **acceptable** / **minor issues** / **unacceptable**.

| Clip | Length | Model | Audio s | Transcribe s | RTF | Rating | Notes |
|------|--------|-------|---------|--------------|-----|--------|-------|
| 1. Technical explanation | ~30s | large-v3-turbo | | | | | |
| 2. Behavioral STAR | ~60s | large-v3-turbo | | | | | |
| 3. System design opening | ~90s | large-v3-turbo | | | | | |

Specific words/terms Whisper got wrong on your accent (worth tracking):

-

**Decision gate:** if any rating is "unacceptable", re-run that clip with
`--model large-v3` and add a row. If still unacceptable on `large-v3`, **stop and
reassess the project**.

Outcome: ☐ proceed on large-v3-turbo &nbsp; ☐ proceed on large-v3 &nbsp; ☐ stop & reassess

---

## Phase 2 — LLM quality sanity check

Setup: `qwen2.5:7b-instruct-q4_K_M` via Ollama, using the 3 Phase 1 transcripts.
(Script: `scripts/analyze_test.py` — created in Phase 2.) &nbsp; Date: _____

For each output, judge the three things from `local-llm-setup.md`:

| Transcript | Upgrade real or generic? | Gaps real or padded? | overall_note pointed or boilerplate? | Schema valid? | Useful? |
|-----------|--------------------------|----------------------|--------------------------------------|---------------|---------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

Measured analysis latency (7B, M4) for a ~90s transcript: _____ s.

**Decision gate:** if fewer than 2 of 3 outputs are clearly useful, pull
`qwen2.5:14b-instruct-q4_K_M`, swap the model name, and re-run. If 14B still isn't
useful, rework the prompt before building UI.

Outcome: ☐ proceed on 7B &nbsp; ☐ proceed on 14B &nbsp; ☐ rework prompt

---

## Dogfooding sessions

After each real practice session, add one entry (per `feedback-loop.md`).
Acceptance criteria (`product-spec.md` §9) needs at least 3. Copy the block below.

### Session N — _____ (date)

- Prompt:
- Did the comparative upgrade teach something? (yes / no / partial):
- Were the lexical gaps real, or did some feel forced? (real / forced / mix):
- Indonesian-isms flagged, and were they accurate?:
- Most useful suggestion of the session (one sentence):
