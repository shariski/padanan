"""Phase 1 Whisper sanity check.

Loads a faster-whisper model and transcribes a single audio file, printing the
transcript plus timing and language-detection diagnostics.

The point of this script (see docs/plan.md Phase 1 and docs/audio-pipeline.md) is
to judge whether transcription quality on Indonesian-accented English is good
enough *before* any app code is built, and to measure transcription latency on
this machine.

Usage:
    uv run python scripts/whisper_test.py <audio_file>
    uv run python scripts/whisper_test.py <audio_file> --model large-v3

The first run downloads the model (~1.5 GB for large-v3-turbo) from Hugging Face.
Decision gate: if a transcript is "unacceptable", re-run with --model large-v3
before going further (docs/plan.md).
"""

import argparse
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel


def transcribe(audio_path: Path, model_name: str) -> None:
    print(f"Loading model '{model_name}' (device=cpu, compute_type=int8)...")
    t0 = time.perf_counter()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print(f"Model loaded in {time.perf_counter() - t0:.1f}s\n")

    print(f"Transcribing {audio_path} ...")
    t1 = time.perf_counter()
    segments, info = model.transcribe(
        str(audio_path),
        language="en",  # force English; avoids language flip on accented speech
        beam_size=5,
        vad_filter=True,  # drop silence, e.g. a late stop-button press
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,  # off for MVP; enabling roughly doubles runtime
        condition_on_previous_text=False,  # avoid hallucination drift on short clips
    )
    # segments is a lazy generator — the real ASR work happens during iteration,
    # so consume it fully before measuring the transcription wall-clock time.
    text = " ".join(seg.text.strip() for seg in segments)
    transcribe_s = time.perf_counter() - t1

    rtf = transcribe_s / info.duration if info.duration else 0.0
    print(
        f"\nlanguage: {info.language} (p={info.language_probability:.2f})  | "
        f"audio: {info.duration:.1f}s  | "
        f"transcribe: {transcribe_s:.1f}s  | "
        f"RTF: {rtf:.2f}x\n"
    )
    print("--- TRANSCRIPT ---")
    print(text)
    print("--- END ---")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Whisper sanity check.")
    parser.add_argument("audio_file", type=Path, help="path to an audio file to transcribe")
    parser.add_argument(
        "--model",
        default="large-v3-turbo",
        help="model name (default: large-v3-turbo; try large-v3 if quality is poor)",
    )
    args = parser.parse_args()

    if not args.audio_file.is_file():
        sys.exit(f"Audio file not found: {args.audio_file}")

    transcribe(args.audio_file, args.model)


if __name__ == "__main__":
    main()
