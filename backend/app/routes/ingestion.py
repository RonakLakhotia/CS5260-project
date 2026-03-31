import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.core.logger import get_logger
from app.models import ProcessRequest, IngestionStatus, VideoMetadata
from app.services.transcript import extract_video_id, get_transcript, semantic_chunk_transcript
from app.services.vector_store import is_video_ingested, ingest_chunks, get_video_metadata
from app.services.metadata import fetch_video_metadata
from app.services.summary import generate_summary

log = get_logger("api.ingestion")
router = APIRouter(tags=["ingestion"])

# In-memory ingestion tracker
ingestions: dict[str, dict] = {}


async def _run_ingestion(video_id: str, youtube_url: str):
    """Background task: fetch metadata → fetch transcript → chunk → embed → store."""
    try:
        # Step 1: fetch video metadata
        ingestions[video_id]["progress"] = "Fetching video metadata"
        log.info("[ingest:%s] Fetching video metadata...", video_id)
        video_meta = await asyncio.to_thread(fetch_video_metadata, youtube_url)
        ingestions[video_id]["metadata"] = video_meta

        # Step 2: fetch transcript
        ingestions[video_id]["progress"] = "Fetching transcript"
        log.info("[ingest:%s] Fetching transcript...", video_id)
        raw = await asyncio.to_thread(get_transcript, youtube_url)
        ingestions[video_id]["progress"] = f"Fetched {len(raw)} raw segments, chunking"
        log.info("[ingest:%s] Got %d raw segments, running semantic chunking...", video_id, len(raw))

        # Step 3 & 4: semantic chunking + summary generation (parallel)
        ingestions[video_id]["progress"] = "Chunking transcript and generating summary"
        log.info("[ingest:%s] Running semantic chunking and summary generation in parallel...", video_id)

        chunks, summary_json = await asyncio.gather(
            asyncio.to_thread(semantic_chunk_transcript, raw),
            generate_summary(raw, video_meta),
        )
        video_meta["summary"] = summary_json
        ingestions[video_id]["metadata"] = video_meta
        log.info("[ingest:%s] %d semantic chunks, summary generated", video_id, len(chunks))

        # Step 5: embed and store (with metadata + summary)
        ingestions[video_id]["progress"] = f"Embedding {len(chunks)} chunks"
        log.info("[ingest:%s] Embedding and storing...", video_id)
        await asyncio.to_thread(ingest_chunks, video_id, youtube_url, chunks, video_meta)

        ingestions[video_id]["status"] = "complete"
        ingestions[video_id]["progress"] = "Done"
        ingestions[video_id]["chunk_count"] = len(chunks)
        log.info("[ingest:%s] Ingestion complete: %d chunks stored", video_id, len(chunks))

    except Exception as e:
        ingestions[video_id]["status"] = "error"
        ingestions[video_id]["progress"] = f"Error: {str(e)}"
        log.error("[ingest:%s] Ingestion failed: %s", video_id, e)


def _build_status(video_id: str, entry: dict) -> IngestionStatus:
    """Build IngestionStatus from in-memory tracker entry."""
    meta = entry.get("metadata")
    return IngestionStatus(
        video_id=video_id,
        status=entry["status"],
        progress=entry["progress"],
        chunk_count=entry.get("chunk_count"),
        metadata=VideoMetadata(**meta) if meta else None,
    )


def _parse_db_metadata(stored: dict) -> VideoMetadata:
    """Convert ChromaDB metadata (str values) back to VideoMetadata."""
    data = dict(stored)
    # ChromaDB stores lists as comma-separated strings
    for field in ("tags", "categories"):
        val = data.get(field, "")
        if isinstance(val, str):
            data[field] = [s.strip() for s in val.split(",") if s.strip()] if val else []
    return VideoMetadata(**data)


def _build_status_from_db(video_id: str) -> IngestionStatus:
    """Build IngestionStatus from ChromaDB collection metadata."""
    stored = get_video_metadata(video_id)
    meta = _parse_db_metadata(stored) if stored else None
    return IngestionStatus(
        video_id=video_id,
        status="complete",
        progress="Ingested",
        metadata=meta,
    )


@router.post("/ingest", response_model=IngestionStatus)
async def ingest_video(
    request: ProcessRequest,
    reingest: bool = Query(False, description="Force re-ingestion even if already ingested"),
):
    """Ingest a YouTube video: fetch transcript, chunk, embed, store in vector DB.

    Runs as a background task. Poll GET /api/ingest/{video_id} for status.
    Pass ?reingest=true to force re-ingestion.
    """
    video_id = extract_video_id(request.youtube_url)
    log.info("Ingestion requested for video %s (reingest=%s)", video_id, reingest)

    if not reingest and is_video_ingested(video_id):
        log.info("Video %s already ingested, skipping (use ?reingest=true to force)", video_id)
        return _build_status_from_db(video_id)

    if not reingest and video_id in ingestions and ingestions[video_id]["status"] == "processing":
        log.info("Video %s ingestion already in progress", video_id)
        return _build_status(video_id, ingestions[video_id])

    # Clear stale in-memory data on reingest
    ingestions[video_id] = {
        "status": "processing",
        "progress": "Starting ingestion",
        "chunk_count": None,
        "metadata": None,
    }

    asyncio.create_task(_run_ingestion(video_id, request.youtube_url))
    log.info("Background ingestion task created for %s", video_id)

    return IngestionStatus(
        video_id=video_id,
        status="processing",
        progress="Starting ingestion",
    )


@router.get("/ingest/{video_id}", response_model=IngestionStatus)
async def get_ingestion_status(video_id: str):
    """Poll ingestion status for a video."""
    if is_video_ingested(video_id):
        return _build_status_from_db(video_id)

    entry = ingestions.get(video_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No ingestion found for this video")

    return _build_status(video_id, entry)
