"""LLM-based router: classify a chat question as transcript- or web-answerable."""

from typing import Literal

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("router")

Route = Literal["transcript", "web"]

_ROUTER_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You route user questions for a 'chat with a YouTube video' app to one of two modes.\n\n"
    "`transcript` — the question is answerable from the video itself (summary, clarification, "
    "explanation, quotes, follow-ups on what was said, topics the video likely covers).\n"
    "`web` — the question needs live internet knowledge the video cannot provide "
    "(current events, real-time data, prices, scores, weather, news, facts about external "
    "topics the video doesn't cover).\n\n"
    "Default to `transcript` whenever ambiguous — users are here to chat with the video. "
    "Use the video title and topic hints to decide borderline cases.\n"
    "Respond with ONLY one word: `transcript` or `web`."
)


async def route_question(
    question: str,
    video_title: str | None = None,
    video_description: str | None = None,
    recent_messages: list[dict] | None = None,
) -> Route:
    """Classify a question as `transcript` or `web`. Falls back to `transcript` on errors."""
    context_lines: list[str] = []
    if video_title:
        context_lines.append(f"Video title: {video_title}")
    if video_description:
        context_lines.append(f"Video description: {video_description[:300]}")
    if recent_messages:
        for m in recent_messages[-2:]:
            context_lines.append(f"{m['role']}: {m['content'][:150]}")

    context = "\n".join(context_lines) if context_lines else "(no prior context)"

    llm = ChatOpenAI(
        model=_ROUTER_MODEL,
        api_key=settings.openai_api_key,
        temperature=0,
        max_tokens=3,
    )
    try:
        resp = await llm.ainvoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQuestion: {question}\n\nMode:"},
        ])
        word = (resp.content or "").strip().lower()
        route: Route = "web" if "web" in word else "transcript"
        log.info("Route=%s q=%.80s", route, question)
        return route
    except Exception as e:
        log.warning("Router failed, defaulting to transcript: %s", e)
        return "transcript"
