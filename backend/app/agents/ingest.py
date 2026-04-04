from app.models import YTSageState
from app.services.transcript import extract_video_id, get_transcript, semantic_chunk_transcript
from app.services.vector_store import ingest_chunks, is_video_ingested
from app.services.metadata import fetch_video_metadata
from app.core.logger import get_logger

log = get_logger("agent.ingest")


async def ingest_transcript(state: YTSageState) -> dict:
    """Fetch transcript, chunk semantically, embed and store in ChromaDB."""
    video_id = extract_video_id(state["youtube_url"])
    log.info("Ingestion node started for video %s", video_id)

    if is_video_ingested(video_id):
        log.info("Video %s already ingested, skipping", video_id)
        return {
            "video_id": video_id,
            "transcript_chunks": [],
            "status": "processing",
        }

    log.info("Fetching metadata for %s", video_id)
    video_meta = fetch_video_metadata(state["youtube_url"])

    log.info("Fetching transcript for %s", video_id)
    raw = get_transcript(state["youtube_url"])

    log.info("Semantic chunking %d raw segments", len(raw))
    chunks = semantic_chunk_transcript(raw)

    log.info("Storing %d chunks in vector DB", len(chunks))
    ingest_chunks(video_id, state["youtube_url"], chunks, video_meta)

    log.info("Ingestion complete for video %s", video_id)
    return {
        "video_id": video_id,
        "transcript_chunks": chunks,
        "status": "processing",
    }
