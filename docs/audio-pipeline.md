# Audio Pipeline

How audio gets from the browser microphone to a transcript the LLM can analyze.

## Pipeline overview

```
Browser MediaRecorder
  → audio blob (webm/opus or mp4/aac depending on browser)
  → POST /api/sessions/<id>/upload
  → saved to data/recordings/<id>.<ext>
  → ffmpeg → 16kHz mono WAV in /tmp (or in-memory)
  → faster-whisper (large-v3 or large-v3-turbo)
  → transcript text + (optional) word timestamps
  → stored in sessions.transcript
  → passed to analyze.py for LLM processing
```

## Browser side

Use `MediaRecorder` with the default mime type for the browser. Do not force a specific codec — Safari and Chrome disagree, and the backend normalizes via ffmpeg anyway.

```javascript
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const recorder = new MediaRecorder(stream);
const chunks = [];
recorder.ondataavailable = (e) => chunks.push(e.data);
recorder.onstop = () => {
  const blob = new Blob(chunks, { type: recorder.mimeType });
  // POST to backend
};
recorder.start();
```

Critical: `navigator.mediaDevices` only exists in a **secure context**. `localhost` qualifies. Over Tailscale, the Tailscale hostname with Tailscale-provided HTTPS qualifies. Plain HTTP over LAN IP will fail silently — the API just isn't there. If recording mysteriously doesn't work on remote, this is the first thing to check.

## Backend conversion

`faster-whisper` accepts most formats but is happiest with 16kHz mono PCM. Use `ffmpeg` for the conversion:

```bash
ffmpeg -i input.webm -ar 16000 -ac 1 -f wav output.wav
```

In Python, either shell out via `subprocess.run` or use `ffmpeg-python`. Shelling out is simpler — pick that unless there's a reason not to.

Conversion is fast (sub-second for a 90-second clip). Doing it synchronously inside the request handler is fine for MVP.

## faster-whisper configuration

Install:

```bash
pip install faster-whisper
```

On Apple Silicon, `faster-whisper` uses CTranslate2's CPU implementation. **Metal/GPU acceleration is not available through faster-whisper at the time of writing.** The CPU path on M4 is acceptable for clips under 120 seconds.

Model choice — try in this order, keep the first that's good enough:

1. **`large-v3-turbo`** (~6x faster than large-v3, claimed quality very close). Try this first.
2. **`large-v3`** (slower, slightly higher accuracy on edge cases). Fall back to this if turbo's accuracy on Indonesian-accented English is noticeably worse.

Smaller models (`medium`, `small`) are not recommended — accent robustness matters for this use case, and the speed savings on short clips don't earn the accuracy hit.

Initialization (done once at app startup):

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    "large-v3-turbo",
    device="cpu",          # Apple Silicon: CPU path is what works
    compute_type="int8",   # int8 quantization, good speed/quality tradeoff
)
```

Note on `compute_type`: `int8` is the speed-optimized option. `int8_float16` is also valid. `float32` is overkill. If accuracy is unacceptable, escalate to `float16` or try `large-v3` first before changing compute type.

Transcription:

```python
segments, info = model.transcribe(
    audio_path,
    language="en",                    # we know the speaker is speaking English
    beam_size=5,                      # default; raises quality slightly vs greedy
    vad_filter=True,                  # filter out silence — helps with stop-button-was-late
    vad_parameters={"min_silence_duration_ms": 500},
    word_timestamps=False,            # not used in MVP — turning this on slows transcription
    condition_on_previous_text=False, # avoid hallucination drift on longer clips
)
transcript = " ".join(seg.text.strip() for seg in segments)
```

`condition_on_previous_text=False` is non-obvious but important — when True, Whisper feeds its own previous output back into context, which can compound hallucination if it gets confused. For short interview clips, off is safer.

`language="en"` is set explicitly. Whisper's language detection sometimes flips on Indonesian-accented English. Forcing English avoids that failure mode entirely.

## Known limitations

These are real and not worth working around in MVP.

### Whisper smooths fillers

Whisper inconsistently transcribes "um", "uh", and false starts. Sometimes they appear, sometimes they don't, and there is no parameter that reliably forces them in. The MVP feedback loop does not depend on detecting fillers. Do not add disfluency post-processing.

### Accent robustness on Indonesian-accented English is not benchmarked

There is no publicly available accuracy benchmark specifically for Indonesian-accented English in Whisper large-v3. General impression is that large-v3 is robust to non-native accents, but this is unverified for this specific accent. **Sanity check task (in `plan.md`):** record 3 short clips early in the build and verify the transcript is acceptable before investing in downstream UI.

### Word-level timestamps are available but cost latency

`word_timestamps=True` roughly doubles transcription time. Not used in MVP. Reserved for a future feature that detects long pauses, which is deferred.

### Initialization cost

Loading the `large-v3-turbo` model takes a few seconds. Load it once at app startup, not per request. The model object is thread-safe enough for a single-user app.

### Memory

`large-v3-turbo` at int8 occupies roughly 1–1.5 GB. Combined with Ollama (~5 GB for Qwen 7B Q4) and the OS, this fits in 16 GB unified memory but doesn't leave headroom for, e.g., running Chrome with 30 tabs. The developer should be aware of this when running everything on one machine.

## Sanity check task

Before building any UI:

1. Record 3 clips at the Mac mini's microphone (built-in or AirPods):
   - 30-second clip explaining a technical concept
   - 60-second clip of a behavioral STAR answer
   - 90-second clip of a system design opening
2. Transcribe each with `large-v3-turbo` at the configuration above.
3. Read each transcript and rate it: acceptable / minor issues / unacceptable.
4. If "unacceptable", re-test with `large-v3` (non-turbo) before going further.
5. Document the result in `docs/dogfooding.md`.

This is in `plan.md` as a checkbox. If the result is "unacceptable" even on `large-v3`, the whole project plan needs to be re-evaluated — stop and reassess.

## What does not go in the audio pipeline

- No noise suppression beyond what the browser already does
- No automatic gain control beyond what the browser already does
- No echo cancellation tuning
- No VAD library beyond what `faster-whisper` includes
- No streaming / chunked transcription — record-then-transcribe is the design

If any of these become necessary based on real-use issues, document the issue first, then propose the addition.
