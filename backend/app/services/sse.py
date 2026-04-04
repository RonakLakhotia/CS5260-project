"""SSE (Server-Sent Events) formatting helpers."""

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """Format a single SSE frame: event: <type>\\ndata: <json>\\n\\n"""
    payload = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


def sse_status(step: str) -> str:
    """Emit a status event indicating current processing step."""
    return format_sse("status", {"step": step})


def sse_error(message: str) -> str:
    """Emit an error event."""
    return format_sse("error", {"message": message})
