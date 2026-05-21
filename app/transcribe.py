"""Whisper transcription (docs/audio-pipeline.md).

The model is loaded once at app startup (see app/main.py lifespan), not per
request — loading large-v3-turbo takes a few seconds. faster-whisper uses the CPU
path on Apple Silicon (Metal isn't supported); acceptable for short clips.
"""

import subprocess
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_NAME = "large-v3-turbo"

_model: WhisperModel | None = None


def load_model() -> None:
    """Load the Whisper model once. Called at app startup."""
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")


def transcribe_audio(audio_path: Path) -> str:
    """Convert to 16kHz mono WAV via ffmpeg, then transcribe. Returns the text.

    Config mirrors scripts/whisper_test.py and docs/audio-pipeline.md: forced
    English, VAD filter, no word timestamps, no conditioning on previous text.
    """
    if _model is None:
        load_model()
    assert _model is not None  # load_model guarantees this

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                str(wav_path),
            ],
            capture_output=True,
            check=True,
        )
        segments, _ = _model.transcribe(
            str(wav_path),
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=False,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        wav_path.unlink(missing_ok=True)
