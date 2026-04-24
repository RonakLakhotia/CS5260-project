import asyncio

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.models import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    MessageRecord,
    SessionRecord,
    SourceChunk,
)
from app.services.transcript import extract_video_id
from app.services.vector_store import query_chunks, get_video_metadata
from app.services.formatting import (
    format_metadata_context,
    format_rag_context,
    extract_detailed_summary,
    ensure_video_ingested,
)
from app.services.conversation import build_history_window
from app.services.router import route_question
from app.services.web_search import stream_web_answer
from app.services.sse import format_sse, sse_status, sse_error
from app.services import chat_store

log = get_logger("api.chat_sessions")
router = APIRouter(prefix="/chat", tags=["chat-sessions"])

# Cosine distance threshold — chunks above this are too irrelevant to show
# ChromaDB cosine distance ranges 0 (identical) to 2 (opposite). Typical relevant chunks: 0.3–1.0
RELEVANCE_THRESHOLD = 1.0
MAX_SOURCES = 3


async def _rewrite_query(question: str, recent_messages: list[dict]) -> str:
    """Rewrite a conversational question into a standalone search query using recent chat context.

    Handles cases like "what did he say about that?" by resolving pronouns and references.
    """
    if not recent_messages:
        return question

    # Only use last 4 messages for context (fast, cheap)
    context_msgs = recent_messages[-4:]
    context = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in context_msgs)

    llm = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)
    response = await llm.ainvoke([
        {"role": "system", "content": (
            "Rewrite the user's latest question into a standalone search query for searching a video transcript. "
            "Resolve pronouns and references using the conversation context. "
            "Return ONLY the rewritten query, nothing else. Keep it concise (under 30 words)."
        )},
        {"role": "user", "content": f"Conversation:\n{context}\n\nLatest question: {question}\n\nRewritten search query:"},
    ])
    rewritten = response.content.strip()
    log.info("Query rewritten: '%s' -> '%s'", question[:60], rewritten[:60])
    return rewritten

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# ── SSE Chat Stream ──────────────────────────────────────────────────────────

async def _stream_chat(chat_id: str, session: dict, question: str, web_search: bool = False):
    """Async generator that streams the chat response as SSE events.

    web_search=True forces the Gemini web-search path. Otherwise an LLM router
    decides per-question whether to answer from the transcript or the live web.
    """
    try:
        video_id = session["video_id"]

        # 1. Save user message
        await chat_store.add_message(chat_id, "user", question)

        # 2. Load history
        yield sse_status("reviewing_history")
        all_messages = await chat_store.get_messages(chat_id)
        running_summary, recent_messages = await build_history_window(session, all_messages)

        # 3. Fetch video metadata once (used by both branches and by the router)
        video_meta = get_video_metadata(video_id) or {}

        # 4. Decide route: explicit override takes priority, else auto-route
        if web_search:
            use_web = True
            log.info("[chat:%s] Route=web (forced by toggle)", chat_id[:8])
        else:
            route = await route_question(
                question,
                video_title=video_meta.get("title"),
                video_description=video_meta.get("description"),
                recent_messages=recent_messages,
            )
            use_web = route == "web"

        if use_web:
            # ── Gemini web search path ── (handles search + answer in one call)
            yield sse_status("searching_web")
            yield sse_status("generating")

            full_response = []
            try:
                async for event in stream_web_answer(question, recent_messages):
                    if event["type"] == "token":
                        full_response.append(event["text"])
                        yield format_sse("token", {"text": event["text"]})
                    elif event["type"] == "sources":
                        yield format_sse("web_sources", {"results": event["results"]})
            except Exception as e:
                log.error("[chat:%s] Gemini web search failed: %s", chat_id[:8], e)
                err_msg = f"Web search failed: {str(e)}"
                full_response.append(err_msg)
                yield format_sse("token", {"text": err_msg})

            # Save and done
            complete_text = "".join(full_response)
            msg_id = await chat_store.add_message(chat_id, "assistant", complete_text)
            yield format_sse("done", {"message_id": msg_id})
            return

        else:
            # ── Video transcript path ──
            meta_context = format_metadata_context(video_meta)
            summary_context = extract_detailed_summary(video_meta)

            # 3. Rewrite query using conversation context, then search
            yield sse_status("searching_transcript")
            search_query = await _rewrite_query(question, recent_messages)
            raw_chunks = query_chunks(video_id, search_query, n_results=5)

            # Filter by relevance score and cap at 3
            relevant = [c for c in raw_chunks if c["distance"] < RELEVANCE_THRESHOLD][:MAX_SOURCES]
            log.info("[chat:%s] RAG: %d/%d chunks passed relevance filter (threshold=%.2f)",
                     chat_id[:8], len(relevant), len(raw_chunks), RELEVANCE_THRESHOLD)
            transcript_context = format_rag_context(relevant)

            # 4. Emit sources early
            yield format_sse("sources", {
                "chunks": [
                    {"text": c["text"][:200], "start_time": c["start_time"], "end_time": c["end_time"]}
                    for c in relevant
                ]
            })

            # 5. Assemble LLM messages
            llm_messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

            if meta_context:
                llm_messages.append({"role": "system", "content": f"--- Video Metadata ---\n{meta_context}"})
            if summary_context:
                llm_messages.append({"role": "system", "content": f"--- Video Summary ---\n{summary_context}"})
            if running_summary:
                llm_messages.append({"role": "system", "content": f"--- Earlier Conversation Summary ---\n{running_summary}"})

            for msg in recent_messages:
                llm_messages.append({"role": msg["role"], "content": msg["content"]})

            llm_messages.append({
                "role": "user",
                "content": f"{question}\n\n--- Relevant Transcript Excerpts ---\n{transcript_context}",
            })

        # 6. Stream LLM tokens
        yield sse_status("generating")
        llm = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.3)

        log.info("[chat:%s] Streaming %s with %d messages...", chat_id[:8], settings.llm_model, len(llm_messages))
        full_response = []
        async for chunk in llm.astream(llm_messages):
            text = chunk.content
            if text:
                full_response.append(text)
                yield format_sse("token", {"text": text})

        # 7. Save complete response to DB
        complete_text = "".join(full_response)
        msg_id = await chat_store.add_message(chat_id, "assistant", complete_text)
        log.info("[chat:%s] Response streamed and saved (msg_id=%d)", chat_id[:8], msg_id)

        # 8. Done
        yield format_sse("done", {"message_id": msg_id})

    except asyncio.CancelledError:
        log.info("[chat:%s] Client disconnected", chat_id[:8])
        raise
    except Exception as e:
        log.error("[chat:%s] Stream error: %s", chat_id[:8], e, exc_info=True)
        yield sse_error(str(e))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new chat session for a YouTube video."""
    video_id = extract_video_id(request.youtube_url)
    log.info("Creating chat session for video %s", video_id)

    ensure_video_ingested(request.youtube_url)

    chat_id = await chat_store.create_session(video_id, request.youtube_url)
    return CreateSessionResponse(chat_id=chat_id, video_id=video_id)


@router.post("/sessions/{chat_id}/messages")
async def send_message(chat_id: str, request: SendMessageRequest):
    """Send a message in a chat session. Returns SSE stream of events."""
    session = await chat_store.get_session(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    log.info("[chat:%s] SSE stream requested (web_search=%s): %.80s", chat_id[:8], request.web_search, request.question)
    return StreamingResponse(
        _stream_chat(chat_id, session, request.question, web_search=request.web_search),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/sessions/{chat_id}/messages", response_model=list[MessageRecord])
async def get_messages(chat_id: str):
    """Get the full message history for a session."""
    session = await chat_store.get_session(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await chat_store.get_messages(chat_id)
    return [MessageRecord(**m) for m in messages]


@router.get("/sessions", response_model=list[SessionRecord])
async def list_sessions(video_id: str = Query(..., description="YouTube video ID")):
    """List all chat sessions for a video."""
    sessions = await chat_store.list_sessions(video_id)
    return [SessionRecord(**s) for s in sessions]
