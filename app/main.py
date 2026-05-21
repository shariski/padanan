"""Padanan FastAPI application.

Phase 3 skeleton: serves a base layout, static assets (HTMX + CSS), and a hello
page that self-tests the HTMX wiring. Run with:

    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Binds 0.0.0.0 so the same server is reachable over Tailscale later (Phase 5);
for now it's localhost-only. No HTTPS in MVP — see docs/CLAUDE.md "Networking".
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Padanan")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/ping", response_class=HTMLResponse)
async def ping() -> str:
    # Skeleton self-test: confirms HTMX actually executes a request, not just that
    # the script loads. Replaced by real routes in Phase 4.
    return "<strong>HTMX works ✓</strong>"
