"""Padanan FastAPI application.

Run with:

    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Binds 0.0.0.0 so the same server is reachable over Tailscale later (Phase 5);
for now it's localhost-only. No HTTPS in MVP — see CLAUDE.md "Networking".

Phase 4: prompt library + session-start screen.
Phase 5: recording flow — POST /api/sessions saves the audio, creates the row,
and returns the session id. Transcription (Phase 6) and analysis (Phase 7) wire
in after.
"""

import json
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db

BASE_DIR = Path(__file__).parent

# Load the curated prompt library once at startup (see docs/product-spec.md §4).
# Single user, small file — module-level load is simpler than a startup event.
with (BASE_DIR / "prompts" / "library.json").open() as f:
    PROMPT_LIBRARY = json.load(f)
PROMPTS_BY_ID = {
    prompt["id"]: prompt
    for category in PROMPT_LIBRARY["categories"]
    for prompt in category["prompts"]
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="Padanan", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def session_start(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "session_start.html", {"library": PROMPT_LIBRARY})


@app.get("/record/{prompt_id}", response_class=HTMLResponse)
async def record_library(request: Request, prompt_id: str) -> HTMLResponse:
    prompt = PROMPTS_BY_ID.get(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Unknown prompt")
    return _recording_screen(request, prompt["text"], "library")


@app.post("/record", response_class=HTMLResponse)
async def record_custom(request: Request, prompt_text: str = Form(...)) -> HTMLResponse:
    prompt_text = prompt_text.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="Custom prompt is empty")
    return _recording_screen(request, prompt_text, "custom")


@app.post("/api/sessions")
async def create_session(
    audio: UploadFile = File(...),
    prompt_text: str = Form(...),
    prompt_source: str = Form(...),
) -> dict:
    prompt_text = prompt_text.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="Missing prompt text")

    # Insert first to get the id, then save the file as <id>.<ext> (product-spec §6).
    session_id = await db.create_session(prompt_text, prompt_source)
    audio_path = f"{session_id}.{_audio_ext(audio.content_type)}"
    (db.RECORDINGS_DIR / audio_path).write_bytes(await audio.read())
    duration = _probe_duration(db.RECORDINGS_DIR / audio_path)
    await db.attach_audio(session_id, audio_path, duration)

    return {"session_id": session_id, "audio_path": audio_path, "duration_seconds": duration}


def _recording_screen(request: Request, prompt_text: str, prompt_source: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "recording.html",
        {"prompt_text": prompt_text, "prompt_source": prompt_source},
    )


def _audio_ext(content_type: str | None) -> str:
    """Map the browser's recording MIME type to a file extension.

    Chrome records audio/webm, Safari audio/mp4. Backend normalizes via ffmpeg
    later (Phase 6), so the exact container only needs to be preserved here.
    """
    if content_type and "mp4" in content_type:
        return "mp4"
    if content_type and "ogg" in content_type:
        return "ogg"
    return "webm"


def _probe_duration(path: Path) -> float:
    """Exact audio duration in seconds via ffprobe (product-spec §5)."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return round(float(result.stdout.strip()), 2)
    except ValueError:
        return 0.0
