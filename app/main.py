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

import asyncio
import json
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analyze, db, transcribe

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
    transcribe.load_model()  # load Whisper once at startup, not per request
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
    full_path = db.RECORDINGS_DIR / audio_path
    full_path.write_bytes(await audio.read())
    await db.attach_audio(session_id, audio_path, _probe_duration(full_path))

    # Transcribe synchronously (MVP, single user). Whisper blocks, so run it off
    # the event loop.
    transcript = await asyncio.to_thread(transcribe.transcribe_audio, full_path)
    await db.set_transcript(session_id, transcript)

    # Analyze. On failure, store an error marker so the results page can surface
    # it loudly (local-llm-setup.md) — never a silent fallback.
    try:
        result = await analyze.analyze(transcript, prompt_text)
        await db.set_analysis(session_id, result.model_dump_json())
    except analyze.AnalysisError as e:
        await db.set_analysis(session_id, json.dumps({"error": str(e)}))

    return {"session_id": session_id, "redirect": f"/sessions/{session_id}"}


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
async def view_session(request: Request, session_id: int) -> HTMLResponse:
    session = await db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # analysis_json holds either a valid Analysis or an {"error": ...} marker.
    analysis = None
    analysis_error = None
    if session["analysis_json"]:
        parsed = json.loads(session["analysis_json"])
        if isinstance(parsed, dict) and "error" in parsed:
            analysis_error = parsed["error"]
        else:
            analysis = parsed

    return templates.TemplateResponse(
        request,
        "session_view.html",
        {"session": session, "analysis": analysis, "analysis_error": analysis_error},
    )


@app.get("/sessions/{session_id}/audio")
async def session_audio(session_id: int) -> FileResponse:
    session = await db.get_session(session_id)
    if session is None or not session["audio_path"]:
        raise HTTPException(status_code=404, detail="Recording not found")
    path = db.RECORDINGS_DIR / session["audio_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Recording file missing")
    return FileResponse(path)


@app.get("/sessions/{session_id}/retry", response_class=HTMLResponse)
async def retry_session(request: Request, session_id: int) -> HTMLResponse:
    """Re-record the same prompt — feedback-loop.md's key active-recall loop."""
    session = await db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _recording_screen(request, session["prompt_text"], session["prompt_source"])


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
