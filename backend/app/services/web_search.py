"""Web search + answer via Gemini with Google Search grounding.

Gemini handles search + answer generation in a single call.
Returns streamed tokens + grounding citations.
"""

from typing import AsyncIterator

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("web_search")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def stream_web_answer(question: str, history: list[dict]) -> AsyncIterator[dict]:
    """Stream a web-grounded answer from Gemini.

    Yields dicts:
      {"type": "token", "text": "..."}        - partial response text
      {"type": "sources", "results": [...]}   - citations (emitted once at end)
    """
    client = _get_client()

    # Build message history (Gemini uses a different format than OpenAI)
    contents = []
    for msg in history[-6:]:  # keep last 6 for context
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=question)]))

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.3,
    )

    log.info("Gemini web search: %s", question[:80])

    full_text_parts: list[str] = []
    grounding_chunks_seen = []

    # Stream the response
    stream = await client.aio.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=contents,
        config=config,
    )
    async for chunk in stream:
        # Yield text tokens
        if chunk.text:
            full_text_parts.append(chunk.text)
            yield {"type": "token", "text": chunk.text}

        # Capture grounding metadata when available
        if chunk.candidates:
            for cand in chunk.candidates:
                gm = getattr(cand, "grounding_metadata", None)
                if gm and getattr(gm, "grounding_chunks", None):
                    for gc in gm.grounding_chunks:
                        web = getattr(gc, "web", None)
                        if web and web.uri not in [s.get("url") for s in grounding_chunks_seen]:
                            grounding_chunks_seen.append({
                                "title": web.title or web.uri,
                                "url": web.uri,
                                "snippet": "",
                            })

    # Emit sources after streaming is done
    if grounding_chunks_seen:
        log.info("Gemini returned %d grounding sources", len(grounding_chunks_seen))
        yield {"type": "sources", "results": grounding_chunks_seen}
    else:
        log.info("Gemini returned no grounding sources")
