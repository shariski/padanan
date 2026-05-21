"""SQLite persistence for Padanan sessions (docs/product-spec.md §5).

No ORM — raw SQL via aiosqlite, one DB file at data/padanan.db. Single user, so
no pooling or concurrency handling beyond SQLite's defaults.
"""

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "padanan.db"
RECORDINGS_DIR = DATA_DIR / "recordings"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY,
    created_at       TEXT NOT NULL,
    prompt_text      TEXT NOT NULL,
    prompt_source    TEXT NOT NULL,
    audio_path       TEXT,
    transcript       TEXT,
    analysis_json    TEXT,
    duration_seconds REAL
);
"""


async def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    RECORDINGS_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(_SCHEMA)
        await conn.commit()


async def create_session(prompt_text: str, prompt_source: str) -> int:
    """Insert a session row (audio not yet saved) and return its id."""
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO sessions (created_at, prompt_text, prompt_source) VALUES (?, ?, ?)",
            (created_at, prompt_text, prompt_source),
        )
        await conn.commit()
        assert cur.lastrowid is not None  # always set after a successful INSERT
        return cur.lastrowid


async def attach_audio(session_id: int, audio_path: str, duration_seconds: float) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE sessions SET audio_path = ?, duration_seconds = ? WHERE id = ?",
            (audio_path, duration_seconds, session_id),
        )
        await conn.commit()


async def set_transcript(session_id: int, transcript: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE sessions SET transcript = ? WHERE id = ?",
            (transcript, session_id),
        )
        await conn.commit()


async def get_session(session_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
