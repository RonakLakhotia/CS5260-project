"""Shared formatting helpers and auto-ingestion logic."""

import json

from app.core.logger import get_logger
from app.services.transcript import extract_video_id, get_transcript, semantic_chunk_transcript
from app.services.vector_store import is_video_ingested, ingest_chunks, get_video_metadata
from app.services.metadata import fetch_video_metadata

log = get_logger("formatting")


def format_metadata_context(meta: dict) -> str:
    """Format video metadata into a readable context block for the LLM."""
    parts = []
    if meta.get("title"):
        parts.append(f"Title: {meta['title']}")
    if meta.get("channel"):
        parts.append(f"Channel/Creator: {meta['channel']}")
    if meta.get("upload_date"):
        parts.append(f"Upload Date: {meta['upload_date']}")
    if meta.get("duration"):
        mins, secs = divmod(int(meta["duration"]), 60)
        parts.append(f"Duration: {mins}m {secs}s")
    if meta.get("language"):
        parts.append(f"Language: {meta['language']}")
    if meta.get("description"):
        parts.append(f"Description: {meta['description']}")
    if meta.get("tags"):
        tags = meta["tags"] if isinstance(meta["tags"], list) else [meta["tags"]]
        parts.append(f"Tags: {', '.join(tags)}")
    if meta.get("categories"):
        cats = meta["categories"] if isinstance(meta["categories"], list) else [meta["categories"]]
        parts.append(f"Categories: {', '.join(cats)}")
    if meta.get("view_count"):
        parts.append(f"Views: {meta['view_count']:,}")
    if meta.get("like_count"):
        parts.append(f"Likes: {meta['like_count']:,}")
    return "\n".join(parts)


def extract_detailed_summary(meta: dict) -> str:
    """Extract the detailed_summary text from the video metadata's summary field."""
    summary_raw = meta.get("summary", "")
    if not summary_raw:
        return ""
    if isinstance(summary_raw, str):
        try:
            summary_dict = json.loads(summary_raw)
        except json.JSONDecodeError:
            return summary_raw
    else:
        summary_dict = summary_raw

    parts = []
    if summary_dict.get("overview"):
        parts.append(summary_dict["overview"])
    if summary_dict.get("detailed_summary"):
        parts.append(summary_dict["detailed_summary"])
    return "\n\n".join(parts) if parts else str(summary_dict)


def ensure_video_ingested(youtube_url: str) -> str:
    """Auto-ingest a video if not already in ChromaDB. Returns video_id."""
    video_id = extract_video_id(youtube_url)
    if is_video_ingested(video_id):
        return video_id

    log.info("Auto-ingesting video %s", video_id)
    video_meta = fetch_video_metadata(youtube_url)
    raw = get_transcript(youtube_url)
    chunks = semantic_chunk_transcript(raw)
    ingest_chunks(video_id, youtube_url, chunks, video_meta)
    return video_id


def format_rag_context(chunks: list[dict]) -> str:
    """Format RAG-retrieved chunks into a transcript context string."""
    return "\n\n".join(
        f"[{c['start_time']:.0f}s - {c['end_time']:.0f}s]: {c['text']}"
        for c in chunks
    )
