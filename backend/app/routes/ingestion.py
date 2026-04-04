import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.logger import get_logger
from app.models import ProcessRequest, IngestionStatus, VideoMetadata
from app.services.transcript import extract_video_id, get_transcript, semantic_chunk_transcript
from app.services.vector_store import is_video_ingested, ingest_chunks, get_video_metadata
from app.services.metadata import fetch_video_metadata
from app.services.summary import generate_summary
from app.services.sse import format_sse, sse_status, sse_error
from app.services import chat_store

log = get_logger("api.ingestion")
router = APIRouter(tags=["ingestion"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

# In-memory ingestion tracker (also used by GET polling fallback)
ingestions: dict[str, dict] = {}


# ── Helper: parse ChromaDB metadata back to VideoMetadata ────────────────────

def _parse_db_metadata(stored: dict) -> VideoMetadata:
    """Convert ChromaDB metadata (str values) back to VideoMetadata."""
    data = dict(stored)
    for field in ("tags", "categories"):
        val = data.get(field, "")
        if isinstance(val, str):
            data[field] = [s.strip() for s in val.split(",") if s.strip()] if val else []
    return VideoMetadata(**data)


# ── SSE Generators ───────────────────────────────────────────────────────────

async def _already_ingested(video_id: str, youtube_url: str):
    """Video exists in ChromaDB — emit metadata + done immediately."""
    stored = get_video_metadata(video_id)
    meta = _parse_db_metadata(stored) if stored else None
    chat_id = await chat_store.create_session(video_id, youtube_url)

    if meta:
        yield format_sse("metadata", meta.model_dump())
    yield format_sse("done", {
        "video_id": video_id,
        "chat_id": chat_id,
        "already_ingested": True,
    })


async def _in_progress(video_id: str):
    """Another request is already processing this video."""
    entry = ingestions.get(video_id, {})
    yield sse_status(entry.get("progress", "processing"))
    yield sse_error("Ingestion already in progress. Poll GET /api/ingest/{video_id} for updates.")


async def _stream_ingestion(video_id: str, youtube_url: str):
    """Full ingestion pipeline as an SSE stream."""
    try:
        # Step 1: Fetch metadata
        yield sse_status("fetching_metadata")
        ingestions[video_id]["progress"] = "Fetching video metadata"
        log.info("[ingest:%s] Fetching video metadata...", video_id)
        video_meta = await asyncio.to_thread(fetch_video_metadata, youtube_url)
        ingestions[video_id]["metadata"] = video_meta

        yield format_sse("metadata", {
            "title": video_meta.get("title", ""),
            "channel": video_meta.get("channel", ""),
            "duration": video_meta.get("duration", 0),
            "thumbnail": video_meta.get("thumbnail", ""),
            "upload_date": video_meta.get("upload_date", ""),
        })

        # Step 2: Fetch transcript
        yield sse_status("fetching_transcript")
        ingestions[video_id]["progress"] = "Fetching transcript"
        log.info("[ingest:%s] Fetching transcript...", video_id)
        raw = await asyncio.to_thread(get_transcript, youtube_url)
        log.info("[ingest:%s] Got %d raw segments", video_id, len(raw))

        # Step 3: Chunk + summarize (parallel)
        yield sse_status("generating_summary")
        ingestions[video_id]["progress"] = "Chunking transcript and generating summary"
        log.info("[ingest:%s] Running semantic chunking and summary generation in parallel...", video_id)

        chunks, summary_json = await asyncio.gather(
            asyncio.to_thread(semantic_chunk_transcript, raw),
            generate_summary(raw, video_meta),
        )
        video_meta["summary"] = summary_json
        ingestions[video_id]["metadata"] = video_meta
        log.info("[ingest:%s] %d semantic chunks, summary generated", video_id, len(chunks))

        # Emit summary
        try:
            summary_data = json.loads(summary_json) if isinstance(summary_json, str) else summary_json
        except (json.JSONDecodeError, TypeError):
            summary_data = {}
        yield format_sse("summary", summary_data)

        # Step 4: Embed and store
        yield sse_status("embedding")
        ingestions[video_id]["progress"] = f"Embedding {len(chunks)} chunks"
        log.info("[ingest:%s] Embedding and storing...", video_id)
        await asyncio.to_thread(ingest_chunks, video_id, youtube_url, chunks, video_meta)

        # Step 5: Create chat session
        chat_id = await chat_store.create_session(video_id, youtube_url)
        log.info("[ingest:%s] Chat session created: %s", video_id, chat_id[:8])

        # Update tracker
        ingestions[video_id]["status"] = "complete"
        ingestions[video_id]["progress"] = "Done"
        ingestions[video_id]["chunk_count"] = len(chunks)
        ingestions[video_id]["chat_id"] = chat_id
        log.info("[ingest:%s] Ingestion complete: %d chunks stored", video_id, len(chunks))

        yield format_sse("done", {
            "video_id": video_id,
            "chat_id": chat_id,
            "chunk_count": len(chunks),
        })

    except asyncio.CancelledError:
        log.info("[ingest:%s] Client disconnected", video_id)
        raise
    except Exception as e:
        log.error("[ingest:%s] Stream error: %s", video_id, e, exc_info=True)
        ingestions[video_id]["status"] = "error"
        ingestions[video_id]["progress"] = f"Error: {str(e)}"
        yield sse_error(str(e))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_video(
    request: ProcessRequest,
    reingest: bool = Query(False, description="Force re-ingestion even if already ingested"),
):
    """Ingest a YouTube video via SSE stream.

    Streams progress events as the pipeline runs: metadata → transcript → summary → embedding → done.
    Pass ?reingest=true to force re-ingestion.
    """
    video_id = extract_video_id(request.youtube_url)
    log.info("Ingestion requested for video %s (reingest=%s)", video_id, reingest)

    # Already ingested — emit metadata + done immediately
    if not reingest and is_video_ingested(video_id):
        log.info("Video %s already ingested", video_id)
        return StreamingResponse(
            _already_ingested(video_id, request.youtube_url),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    # Already in progress
    if not reingest and video_id in ingestions and ingestions[video_id]["status"] == "processing":
        log.info("Video %s ingestion already in progress", video_id)
        return StreamingResponse(
            _in_progress(video_id),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    # Initialize tracker
    ingestions[video_id] = {
        "status": "processing",
        "progress": "Starting ingestion",
        "chunk_count": None,
        "metadata": None,
        "chat_id": None,
    }

    return StreamingResponse(
        _stream_ingestion(video_id, request.youtube_url),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ── Polling Fallback ─────────────────────────────────────────────────────────

def _build_status(video_id: str, entry: dict) -> IngestionStatus:
    """Build IngestionStatus from in-memory tracker entry."""
    meta = entry.get("metadata")
    return IngestionStatus(
        video_id=video_id,
        status=entry["status"],
        progress=entry["progress"],
        chunk_count=entry.get("chunk_count"),
        chat_id=entry.get("chat_id"),
        metadata=VideoMetadata(**meta) if meta else None,
    )


@router.get("/ingest/{video_id}", response_model=IngestionStatus)
async def get_ingestion_status(video_id: str):
    """Poll ingestion status (fallback for SSE reconnection)."""
    # Check in-memory tracker first
    entry = ingestions.get(video_id)
    if entry:
        return _build_status(video_id, entry)

    # Fall back to ChromaDB check
    if is_video_ingested(video_id):
        stored = get_video_metadata(video_id)
        meta = _parse_db_metadata(stored) if stored else None
        return IngestionStatus(
            video_id=video_id,
            status="complete",
            progress="Ingested",
            metadata=meta,
        )

    raise HTTPException(status_code=404, detail="No ingestion found for this video")
