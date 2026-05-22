"""LLM analysis via Ollama (docs/local-llm-setup.md, docs/feedback-loop.md).

Takes the interview prompt + transcript and returns a validated Analysis: the
senior-IC upgrade, lexical gaps, Indonesian-isms, and an overall note.

The system prompt — the highest-leverage code in the project — lives in
app/prompts/analyze_system.txt (the single source of truth, also used by
scripts/analyze_test.py). It was tightened over three iterations in Phase 2.

On malformed output it retries once with a strict reminder, then raises
AnalysisError; on an unreachable Ollama it raises AnalysisError immediately. It
never silently returns degraded output — the schema is the contract.
"""

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "analyze_system.txt").read_text()

RETRY_REMINDER = (
    "Your previous response did not match the required JSON schema. Respond again "
    "with ONLY valid JSON matching exactly the schema specified in the system "
    "prompt. No prose before or after the JSON."
)


class Gap(BaseModel):
    spoken: str
    suggested: str
    reason: str


class ContentNote(BaseModel):
    kind: str  # "missing" | "weak" | "check"
    note: str


class Analysis(BaseModel):
    transcript_cleaned: str
    upgraded_version: str
    lexical_gaps: list[Gap]
    indonesian_isms: list[Gap]
    content_feedback: list[ContentNote] = []
    overall_note: str


class AnalysisError(Exception):
    """Raised when analysis cannot produce a valid Analysis (after one retry)."""


def _user_prompt(prompt_text: str, transcript: str) -> str:
    return (
        f"INTERVIEW PROMPT:\n{prompt_text}\n\n"
        f"SPEAKER'S ANSWER (transcript):\n{transcript}\n\n"
        "Produce the analysis JSON."
    )


async def analyze(transcript: str, prompt_text: str) -> Analysis:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(prompt_text, transcript)},
    ]
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in (1, 2):
            try:
                content = await _chat(client, messages)
            except httpx.HTTPError as e:
                # Ollama down/unreachable — retrying won't help (product-spec §8).
                raise AnalysisError(f"could not reach Ollama ({e})") from e
            try:
                return Analysis.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError) as e:
                if attempt == 2:
                    raise AnalysisError("model returned malformed output") from e
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": RETRY_REMINDER})
    raise AnalysisError("unreachable")  # loop always returns or raises


async def _chat(client: httpx.AsyncClient, messages: list[dict]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 2000},
    }
    r = await client.post(OLLAMA_URL, json=payload)
    r.raise_for_status()
    return r.json()["message"]["content"]
