"""Padanan FastAPI application.

Run with:

    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Binds 0.0.0.0 so the same server is reachable over Tailscale later (Phase 5);
for now it's localhost-only. No HTTPS in MVP — see CLAUDE.md "Networking".

Phase 4: the prompt library is loaded once at startup; the home page is the
session-start screen (Library + Custom), and selecting a prompt navigates to the
recording screen with the prompt rendered. (Recording controls arrive in Phase 5.)
"""

import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

app = FastAPI(title="Padanan")
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


def _recording_screen(request: Request, prompt_text: str, prompt_source: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "recording.html",
        {"prompt_text": prompt_text, "prompt_source": prompt_source},
    )
