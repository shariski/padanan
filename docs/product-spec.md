# Product Spec — Padanan

This document specifies the MVP. Anything not in this document is out of scope. Deferred ideas live in [`risks.md`](risks.md).

## 1. The problem in one paragraph

The developer is a tech lead in Indonesia, native Bahasa Indonesia, B2-upper English, prepping for senior IC remote interviews at global companies. Grammar is acceptable. Accent is intelligible. The real bleed during interviews is **lexical retrieval**: the precise word ("idempotent", "back-pressure", "tail latency", "mitigate") does not arrive in time, so the answer settles for a vague substitute ("the same again", "too much load", "slow", "fix"). The result sounds less senior than the developer is, and momentum drops mid-answer.

Pronunciation, filler frequency, and grammar slips are real but rank lower in pain. The MVP addresses retrieval only.

## 2. User flow

A single user (the developer). One device at a time. Either Mac mini in front of him, or iPhone Safari via Tailscale while away from the desk.

The flow:

1. Open the app. Land on the **session start** screen.
2. Choose a prompt source:
   - **Pick from library** (curated list, see §4)
   - **Paste custom prompt** (a question the developer wants to rehearse, e.g. from a real upcoming interview)
3. The prompt appears full-screen. A **Record** button is visible.
4. Tap Record. Browser asks for microphone permission the first time. Recording starts; a visible timer counts up. A **Stop** button appears.
5. Speak the answer. Stop when done. Soft cap at 120 seconds; the UI does not auto-stop, but it shows the timer in red after 120s as a hint that the analysis works best on shorter clips.
6. After Stop, the audio uploads. The UI shows "Transcribing…" then "Analyzing…".
7. The **results screen** appears, showing:
   - Original prompt (collapsed by default, expandable)
   - **Transcript** of what was said
   - **Senior-IC native upgrade** — same content, upgraded vocabulary and discourse markers
   - **Lexical gaps** — a list of 3 to 8 items, each containing:
     - The phrase the speaker used
     - The suggested phrase
     - A one-sentence reason
   - **Indonesian-isms** (if any detected) — same structure as lexical gaps but flagged separately
   - A **Retry** button (rerecord the same prompt) and a **New session** button
8. All sessions are persisted (see §6) and listed on a separate **history** screen, accessible from a sidebar / top link.

The user can leave the results page and come back to it from history. There is no editing of past sessions.

## 3. UI surfaces

Three screens. No more.

### 3.1 Session start

- Title: "Padanan"
- Two tabs or buttons: "Library" and "Custom"
- Library shows a list of prompt categories (see §4); selecting a category shows prompts in that category; selecting a prompt advances to recording
- Custom shows a single textarea + "Use this prompt" button

### 3.2 Recording + analyzing

- The prompt is shown in large text at the top
- Below: a single big button — "Record" → "Stop"
- Below the button: a timer (mm:ss). Black up to 90s, amber 90–120s, red past 120s
- After Stop: the button is replaced by status text — "Transcribing…", then "Analyzing…"
- This screen also shows a back arrow so the user can abandon a session

### 3.3 Results

- Prompt (collapsed by default)
- Transcript (plain text, with a small "play original recording" button)
- Side by side or stacked (depending on viewport width): Transcript vs Upgraded version
- Lexical gaps list
- Indonesian-isms list (only shown if non-empty)
- Retry / New session

### 3.4 History (secondary)

- A reverse-chronological list of past sessions: timestamp, prompt (truncated), and a thumbnail of the first lexical gap suggestion as a teaser
- Clicking a row opens the results screen for that session

## 4. Prompt library

A small, hand-curated set. Not generated, not extensible via UI in MVP. Lives in `app/prompts/` as JSON files. Initial categories and counts:

- **System design** (4 prompts)
  - "Walk me through how you'd design a URL shortener for a service expecting 100M URLs."
  - "Design a notification system that supports email, push, and SMS at 10K notifications/second."
  - "How would you architect a feature flag service for a multi-region SaaS product?"
  - "Design a job queue that guarantees at-least-once delivery with backoff."
- **Technical deep-dive** (3 prompts)
  - "Explain how database sharding works and the trade-offs you'd consider."
  - "Walk me through what happens, in detail, when a user types a URL and hits enter."
  - "Describe how you'd debug a production service whose p99 latency suddenly doubled."
- **Behavioral / leadership** (4 prompts)
  - "Tell me about a time you had to disagree with your manager."
  - "Describe the most technically complex project you've led."
  - "How do you handle an underperforming team member?"
  - "Tell me about a time you made a wrong technical decision and how you recovered."
- **Past project walkthrough** (2 prompts)
  - "Walk me through a system you built or significantly contributed to in the last two years."
  - "Describe a technical decision you championed that turned out to be the right call, and explain why."

Total: 13 prompts. Enough to rehearse without overwhelming.

## 5. Data model

SQLite. Two tables.

### `sessions`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY | |
| created_at | TEXT | ISO 8601 |
| prompt_text | TEXT | The actual prompt used, captured verbatim |
| prompt_source | TEXT | `library` or `custom` |
| audio_path | TEXT | Relative path under `data/recordings/` |
| transcript | TEXT | Whisper output |
| analysis_json | TEXT | The full JSON returned by the LLM (see §7) |
| duration_seconds | REAL | From the audio file |

### `prompts_library`

Optional. If the library is loaded from JSON files on disk, this table can be skipped. Pick one approach and stay consistent.

## 6. Storage

- Audio files: `data/recordings/<session_id>.webm` (or `.mp4` depending on browser format). Gitignored.
- DB: `data/padanan.db`. Gitignored.
- Recordings are retained indefinitely in MVP. There is no UI to delete sessions. If disk grows too large after weeks of use, the developer will deal with it manually.

## 7. Analysis JSON schema

The LLM returns JSON matching this shape exactly. The prompt enforces it. The backend validates and re-prompts once if the shape is wrong.

```json
{
  "transcript_cleaned": "string — the transcript with obvious ASR artifacts cleaned up but content preserved",
  "upgraded_version": "string — the senior-IC native upgrade of the same content",
  "lexical_gaps": [
    {
      "spoken": "string — the phrase as the speaker said it",
      "suggested": "string — the recommended phrase",
      "reason": "string — one sentence, plain English"
    }
  ],
  "indonesian_isms": [
    {
      "spoken": "string",
      "suggested": "string",
      "reason": "string — one sentence explaining the Indonesian-language pattern that leaked through"
    }
  ],
  "content_feedback": [
    {
      "kind": "string — missing | weak | check",
      "note": "string — a substance observation specific to this answer; check items are framed as 'verify whether…', never verdicts"
    }
  ],
  "overall_note": "string — one or two sentences, the single most useful observation about this answer"
}
```

`lexical_gaps` is the headline. The prompt asks for 3 to 8 items. `indonesian_isms` may be empty. `content_feedback` is a separate substance layer (missing/weak/check) and may also be empty; it flags points to verify, it does not authoritatively grade correctness.

## 8. What is explicitly out of scope for MVP

These are not "v2" features. They are decisions to not build, full stop, in week one. If they prove valuable after MVP dogfooding, they can be considered then. Until then, they are noise.

- Filler word detection, pause detection, word-level timing display
- Pronunciation analysis or scoring
- Personal vocabulary corpus (a growing list of words the developer wants to activate)
- Spaced repetition or re-prompting based on past gaps
- Cross-session pattern surfacing ("you keep pausing on distributed-systems terms")
- Streaming transcription
- Editing past sessions or tagging them
- Sharing or exporting sessions
- Multi-user, auth, accounts
- A mobile-native app
- Browser extension
- Anything that touches Claude API, OpenAI API, or any cloud LLM
- Offline operation when there is no Ollama process running (the app simply shows an error)

## 9. Acceptance criteria

The MVP is complete when:

- [~] The developer can run `uvicorn app.main:app --host 0.0.0.0` and open the app from the Mac mini and from his iPhone via Tailscale — _Mac mini: done. Tailscale is up and the app is reachable over the tailnet (HTTP 200 on the Mac's Tailscale IP), so the iPhone can view sessions/history. iPhone **recording** is blocked by the secure-context requirement (`getUserMedia` needs HTTPS) — the tailnet's HTTPS certs aren't enabled. Fix: enable HTTPS in the Tailscale admin console, then `tailscale serve` port 8000._
- [x] All 13 library prompts are loadable and recordable
- [x] Custom prompts work end to end
- [~] A full session (open → record 60s → stop → transcribe → analyze → results displayed) completes in under 45 seconds on the Mac mini M4 16GB — _met for short clips (~33s clip → ~33s); a 60s clip extrapolates to ~45–55s, so marginally missed at 60s+. Dominated by Qwen analysis; accepted local-inference tradeoff (see `dogfooding.md`)._
- [x] Past sessions appear in history and reopen correctly
- [x] The developer has dogfooded the app for at least 3 real practice sessions and recorded informal notes about whether the feedback was useful, in `docs/dogfooding.md` (created during build)
- [x] The Whisper accuracy sanity check (see `audio-pipeline.md`) has been run and the result documented
- [x] The LLM output quality sanity check (see `local-llm-setup.md`) has been run and the result documented
