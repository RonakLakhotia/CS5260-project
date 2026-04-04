from fastapi import APIRouter
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import STATELESS_CHAT_SYSTEM_PROMPT
from app.models import ChatRequest, ChatResponse, SourceChunk
from app.services.transcript import extract_video_id
from app.services.vector_store import query_chunks, get_video_metadata
from app.services.formatting import format_metadata_context, format_rag_context, ensure_video_ingested

log = get_logger("api.chat")
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, deprecated=True)
async def chat_about_video(request: ChatRequest):
    """Stateless chat — single question/answer, no history.

    Deprecated: use POST /api/chat/sessions/{chat_id}/messages for session-based chat.
    """
    video_id = extract_video_id(request.youtube_url)
    log.info("Chat request for video %s: %.80s", video_id, request.question)

    ensure_video_ingested(request.youtube_url)

    video_meta = get_video_metadata(video_id) or {}
    meta_context = format_metadata_context(video_meta)

    relevant = query_chunks(video_id, request.question, n_results=5)
    transcript_context = format_rag_context(relevant)

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )

    log.info("Calling %s for chat answer...", settings.llm_model)
    response = await llm.ainvoke([
        {"role": "system", "content": STATELESS_CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Question: {request.question}\n\n"
            f"--- Video Info ---\n{meta_context}\n\n"
            f"--- Transcript Excerpts ---\n{transcript_context}"
        )},
    ])

    log.info("Chat response generated for video %s", video_id)
    return ChatResponse(
        answer=response.content,
        sources=[
            SourceChunk(text=c["text"][:200], start_time=c["start_time"], end_time=c["end_time"])
            for c in relevant
        ],
    )
