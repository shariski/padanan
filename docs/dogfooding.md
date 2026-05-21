# Dogfooding Log

Results from the sanity-check gates and ongoing real-use notes. Referenced by
`plan.md` (Phases 1, 2, 10), `product-spec.md` §9, `audio-pipeline.md`,
`local-llm-setup.md`, and `feedback-loop.md`.

The two sanity checks below are **decision gates** — if a gate fails, stop and
reassess before building further (see `plan.md` stop conditions).

---

## Phase 1 — Whisper accuracy sanity check

Setup: `large-v3-turbo`, CPU, int8, via `scripts/whisper_test.py`.
Hardware: Mac mini M4 16GB. &nbsp; Mic: built-in (Voice Memos). &nbsp; Date: 2026-05-21

Rate each transcript: **acceptable** / **minor issues** / **unacceptable**.

| Clip | Length | Model | Audio s | Transcribe s | RTF | Rating | Notes |
|------|--------|-------|---------|--------------|-----|--------|-------|
| 1. Technical explanation | 33.5s | large-v3-turbo | 33.5 | 9.9 | 0.30x | acceptable | Technical terms (API, backend, endpoint) transcribed cleanly. "application program interface" is the developer's actual wording, not an ASR error (confirmed). No transcription errors. |
| 2. Behavioral STAR | ~60s | large-v3-turbo | — | — | — | not recorded | Gate passed on clip 1; developer chose not to record more. |
| 3. System design opening | ~90s | large-v3-turbo | — | — | — | not recorded | Gate passed on clip 1; developer chose not to record more. |

Specific words/terms Whisper got wrong on your accent (worth tracking):

- None on clip 1. ("program" vs "programming" was confirmed as the developer's actual word choice, not an ASR error — and is itself the kind of lexical gap the app's analysis step is meant to surface.)
- Clip 2 (rate-limiter, 112s): "Rust" was mis-transcribed as "RAS" (and once as "radius") — a real ASR error on a technical term in the developer's accent. Everything else transcribed correctly. Not severe enough to fail the gate (the LLM upgrade step auto-corrected it to "Rust"), but the first concrete instance of the accent-on-technical-terms risk flagged in `audio-pipeline.md`.

**Decision gate:** if any rating is "unacceptable", re-run that clip with
`--model large-v3` and add a row. If still unacceptable on `large-v3`, **stop and
reassess the project**.

Outcome: ☑ **proceed on large-v3-turbo** &nbsp; ☐ proceed on large-v3 &nbsp; ☐ stop & reassess &nbsp; — _gate passed 2026-05-21 on a single 30s clip by developer's decision; transcription clearly acceptable._

---

## Phase 2 — LLM quality sanity check

Setup: `qwen2.5:7b-instruct-q4_K_M` via Ollama, using the 3 Phase 1 transcripts.
(Script: `scripts/analyze_test.py` — created in Phase 2.) &nbsp; Date: 2026-05-21

For each output, judge the three things from `local-llm-setup.md`:

| Run | Upgrade real or generic? | Gaps real or padded? | overall_note pointed or boilerplate? | Schema valid? | Useful? |
|-----------|--------------------------|----------------------|--------------------------------------|---------------|---------|
| clip1 (basic "what is an API", base prompt) | modest | padded / clause-level | boilerplate ("Keep up the good work!") | yes | no — but input too basic to fairly judge |
| clip2 (rate limiter, prompt v2 "tightened") | good | mediocre (banned phrases reworded as synonyms) | good (no praise) | yes | partial |
| clip2 (rate limiter, prompt v3 "effect-reframe + de-leak") | good | mostly real (reasons state concrete effects) | pointed, domain-correct | yes | yes |

Three prompt iterations were needed; the base prompt from `local-llm-setup.md` produced
the `feedback-loop.md` anti-patterns (empty praise, generic reasons, invented
Indonesian-isms). Fixes that worked: (1) a positive "every reason must name a concrete
effect" self-test instead of a banned-phrase blocklist — the model evaded the blocklist
with synonyms; (2) GOOD/BAD few-shot exemplars marked "form only — do not copy" — until
then the model parroted example nouns ("idempotency", "backpressure") into unrelated
domains; (3) pushing the `indonesian_isms` prior toward `[]`. Residual 7B limitation: it
polishes disfluency well but does not proactively inject missing senior-IC domain
vocabulary (it never suggested "token bucket"/"sliding window" for the rate-limiter
answer). Qwen 14B remains the documented lever if this matters in real dogfooding.

Measured analysis latency (7B, M4) for the 112s clip2 transcript: ~33–45s (cold/warm),
schema-valid on the first attempt every run.

**Decision gate:** if fewer than 2 of 3 outputs are clearly useful, pull
`qwen2.5:14b-instruct-q4_K_M`, swap the model name, and re-run. If 14B still isn't
useful, rework the prompt before building UI.

Outcome: ☑ **proceed on 7B (with the tightened prompt in `scripts/analyze_test.py`)** &nbsp; ☐ proceed on 14B &nbsp; ☐ rework prompt &nbsp; — _gate passed 2026-05-21; see notes above._

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
