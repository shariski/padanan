# Risks and Unknowns

Things that could break the MVP, and things we chose not to build. Read this alongside `plan.md` — many of the "stop and reassess" gates correspond to entries here.

## Known unknowns

### Whisper accuracy on Indonesian-accented English

**Risk:** Whisper large-v3 is generally robust to non-native accents, but there is no public benchmark specifically for Indonesian-accented English. Transcription quality might be lower than expected.

**Mitigation:** Phase 1 of `plan.md` is a sanity check with 3 real clips before building anything around the transcription layer.

**Fallback:** If `large-v3-turbo` is unacceptable, fall back to `large-v3`. If that's also unacceptable, the project's foundational assumption is wrong and the plan needs to be revised — possibly switching to a different ASR (e.g. cloud Whisper API, even though the developer wanted local).

### Qwen 7B output quality

**Risk:** The lexical-upgrade task demands nuance. A 7B local model might produce flat or generic upgrades, padded gap lists, or boilerplate overall_notes.

**Mitigation:** Phase 2 of `plan.md` is a sanity check on 3 transcripts before building UI.

**Fallback:** Upgrade to Qwen 14B Q4 (one config change). If that's also insufficient, the prompt needs more work, or the model needs to be different (Llama 3.1 8B for comparison), or — last resort — the self-hosting constraint needs to be relaxed.

### Ollama JSON-mode reliability

**Risk:** `"format": "json"` forces JSON-shaped output but doesn't guarantee schema correctness. The model might omit fields or invent fields.

**Mitigation:** Pydantic validation with one strict re-prompt on failure.

**Fallback:** If the failure rate is high in dogfooding, tighten the system prompt with explicit field-by-field guidance, or switch to a 14B model where instruction-following is stronger.

### M4 16GB memory pressure

**Risk:** Running Whisper large-v3-turbo (~1.5GB) + Qwen 7B Q4 (~5GB) + macOS + browser leaves limited headroom. Heavy use could push the system into swap, hurting latency.

**Mitigation:** Close memory-heavy apps during use. Monitor with Activity Monitor during Phase 1 and Phase 2.

**Fallback:** If 14B is needed and 16GB is too tight, options are (a) accept slower swap-driven latency, (b) close more apps, (c) accept that Qwen 7B is the ceiling on this hardware.

### Tailscale + browser microphone secure-context interaction

**Risk:** `MediaRecorder` requires a secure context. Tailscale provides HTTPS via its MagicDNS hostnames if HTTPS certificates are enabled, but the developer may not have enabled them. Falling back to plain HTTP over the Tailscale IP will make `navigator.mediaDevices` undefined.

**Mitigation:** Enable Tailscale HTTPS certificates before testing remote recording. Documented in `audio-pipeline.md`.

**Fallback:** If remote recording doesn't work, the app is Mac-only. Annoying but not project-killing.

### Whisper transcription latency on M4 CPU

**Risk:** faster-whisper on Apple Silicon uses CPU (no Metal path). Latency on a 90-second clip is "probably acceptable" but unverified. Could be 5 seconds; could be 30.

**Mitigation:** Measure during Phase 1.

**Fallback:** If latency is too long, try `large-v3-turbo` (already the default) or fall back to `medium` accepting the accent-robustness hit.

## Things we chose not to build (and why)

### Filler / pause / disfluency detection

The original brainstorm considered detecting "um", "uh", false starts, and long mid-sentence pauses as signals of word-finding trouble. We deferred this because:

- Whisper's filler behavior is inconsistent; building on top of unstable input is bad scope discipline
- Word-level timestamps double transcription time
- The comparative-output design already addresses word-finding indirectly: if a word was hard to find, the upgrade often shows what the speaker was reaching for
- It can be added in a future iteration once the basic loop is dogfooded

### Personal vocabulary corpus

The idea: every gap surfaced becomes an entry in a growing personal vocab list, queryable across sessions. We deferred because:

- It only earns its keep after many sessions, which week one cannot produce
- Without spaced repetition or active recall, the corpus is just a log
- It is a real candidate for a v2 build if dogfooding reveals the gaps are recurring in predictable ways

### Spaced repetition / re-prompting

The idea: 24 hours after a gap is surfaced, re-prompt the user with a similar question that forces re-use of the suggested word. Powerful for retrieval practice, but:

- Requires the vocabulary corpus to exist first
- Requires a scheduling/notification mechanism we didn't want in MVP
- Likely the highest-value v2 feature, but only after MVP validates the rest

### Cross-session pattern surfacing

The idea: after N sessions, surface aggregated patterns ("you pause on distributed-systems terms 70% of the time"). Deferred because:

- Needs N sessions of clean data first
- The local 7B model's gap-detection isn't stable enough across sessions for aggregation to be statistically meaningful

### Pronunciation analysis

The idea: phoneme-level acoustic comparison to flag mispronunciations. Out of scope because:

- Requires specialized acoustic models, not LLMs
- Not the developer's main pain point at B2 upper
- Even if built, accent reduction is a marginal interview-prep gain compared to lexical retrieval

### Real-time / streaming feedback

The idea: as the user pauses, suggestions appear. Out of scope because:

- Interrupting mid-answer trains the wrong skill (the skill is sustained delivery)
- Real interviews don't interrupt with corrections — practicing in unrealistic conditions is wasted practice
- Streaming transcription and streaming LLM are both doable but expensive in week-one scope

### Cloud LLM fallback

The idea: if Ollama is down or quality is poor, fall back to Claude API. Excluded because:

- The developer explicitly chose self-hosting; cloud fallback dilutes that choice
- A fallback that's "the better option" is the option that will silently become the only one used
- If self-hosting genuinely doesn't work, that's a learning outcome and a design conversation, not a code branch

### Lenovo Legion as LLM host

The idea: use the GPU on the Lenovo Legion Y520 for LLM inference, offloading from the Mac mini. Excluded because:

- GPU + VRAM unconfirmed (likely GTX 1050/1060 era; possibly only 3–4GB VRAM)
- Adds network hop, dual-machine management, and noise for a question the developer has not answered ("is the Lenovo even useful for this")
- Belongs in a separate learning track, not this MVP

### Tests for everything

The idea: comprehensive test coverage. Excluded because:

- One-week personal app
- The hardest code to "test" (prompt quality, Whisper accuracy) is exactly the code that mocked tests cannot validate
- Prompt construction is the one layer where tests earn their keep, and that's covered in `CLAUDE.md`

## Things that might surprise during the build

- **macOS Gatekeeper / mic permission** quirks on first browser run — the OS-level mic permission prompt is separate from the browser's
- **Ollama model first-run delay** — the first request after `ollama serve` starts can be slow because the model is being loaded into memory
- **Safari `MediaRecorder` quirks** — Safari only relatively recently supported `MediaRecorder`; some codec defaults are different from Chrome
- **Browser audio file extension confusion** — the blob's mime type and the file extension might disagree; ffmpeg handles either, but logging the mime type at upload helps debug
- **HTMX response expectations** — HTMX expects HTML fragments back from POST routes by default, not JSON; structure the routes accordingly
