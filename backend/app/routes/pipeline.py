import asyncio
import hashlib
import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.services import chat_store
from app.models import (
    ProcessRequest,
    JobResponse,
    StatusResponse,
    ResultResponse,
    ConceptResult,
)
from app.agents.graph import build_graph

log = get_logger("api.pipeline")
router = APIRouter(tags=["pipeline"])

jobs: dict[str, dict] = {}

pipeline = build_graph()


async def _run_pipeline(job_id: str, youtube_url: str):
    """Background coroutine that runs the full LangGraph pipeline."""
    try:
        jobs[job_id]["progress"] = "Ingesting transcript"
        log.info("[pipeline:%s] Starting pipeline for %s", job_id[:8], youtube_url)

        initial_state = {
            "youtube_url": youtube_url,
            "video_id": "",
            "transcript_chunks": [],
            "top_concepts": [],
            "scripts": [],
            "citations": [],
            "video_urls": [],
            "slideshow_path": "",
            "status": "processing",
            "error_message": "",
        }

        # Stream pipeline events to update progress per node.
        # astream yields {node_name: output} after each node completes,
        # so we report what starts *next* (the just-finished node is done).
        next_step = {
            "ingest": "Identifying key concepts",
            "planner": "Designing infographic scripts",
            "script_writer": "Generating images and stitching video",
            "video_generator": "Finalizing",
        }
        jobs[job_id]["progress"] = "Ingesting transcript into vector DB"

        result = None
        async for event in pipeline.astream(initial_state):
            for node_name, node_output in event.items():
                if node_name in next_step:
                    jobs[job_id]["progress"] = next_step[node_name]
                result = node_output

        if result is None or result.get("status") == "error":
            jobs[job_id]["status"] = "error"
            err = (result or {}).get("error_message", "Unknown error")
            jobs[job_id]["progress"] = err
            log.error("[pipeline:%s] Pipeline error: %s", job_id[:8], err)
            return

        # Map video_urls to concepts by matching concept_title
        video_url_map = {}
        for v in result.get("video_urls", []):
            video_url_map[v.get("concept_title", "")] = v.get("infographic_urls", [])

        concepts = []
        for concept in result.get("top_concepts", []):
            title = concept.get("title", "")
            concepts.append(ConceptResult(
                title=title,
                description=concept.get("description", ""),
                start_time=concept.get("start_time", 0),
                end_time=concept.get("end_time", 0),
                infographic_urls=video_url_map.get(title, []),
            ))

        slideshow_path = result.get("slideshow_path")

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = "Done"
        jobs[job_id]["result"] = ResultResponse(
            youtube_url=youtube_url,
            concepts=concepts,
            slideshow_url=f"/api/slideshow/{job_id}" if slideshow_path else None,
        )
        jobs[job_id]["slideshow_path"] = slideshow_path
        log.info("[pipeline:%s] Pipeline complete: %d concepts", job_id[:8], len(concepts))

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = f"Error: {str(e)}"
        log.error("[pipeline:%s] Pipeline failed: %s", job_id[:8], e, exc_info=True)


@router.post("/process", response_model=JobResponse)
async def process_video(request: ProcessRequest):
    """Submit a YouTube URL for full processing."""
    job_id = str(uuid.uuid4())
    log.info("Process requested for %s -> job %s", request.youtube_url, job_id[:8])
    jobs[job_id] = {
        "status": "processing",
        "progress": "Starting pipeline",
        "youtube_url": request.youtube_url,
        "result": None,
        "slideshow_path": None,
    }
    asyncio.create_task(_run_pipeline(job_id, request.youtube_url))

    # Store job ID in SQLite so any client can find it
    from app.services.transcript import extract_video_id
    try:
        vid = extract_video_id(request.youtube_url)
        asyncio.create_task(chat_store.set_pipeline_job(vid, job_id))
    except Exception:
        pass

    return JobResponse(job_id=job_id)


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(status=job["status"], progress=job["progress"])


@router.get("/result/{job_id}")
async def get_result(job_id: str):
    """Get completed job results."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Job not complete yet")
    return job["result"]


@router.get("/slideshow/{job_id}")
async def get_slideshow(job_id: str):
    """Serve the generated slideshow MP4 by job ID."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. Use /api/slideshow/video/{video_id} instead.")
    path = job.get("slideshow_path")
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No slideshow available")
    return FileResponse(path, media_type="video/mp4", filename="slideshow.mp4")


@router.get("/slideshow/video/{video_id}")
async def get_slideshow_by_video(video_id: str):
    """Serve slideshow by video ID. Checks SQLite first, then filesystem."""
    # 1. Check SQLite for persisted path
    video = await chat_store.get_video(video_id)
    if video and video.get("slideshow_path") and os.path.isfile(video["slideshow_path"]):
        return FileResponse(video["slideshow_path"], media_type="video/mp4", filename="slideshow.mp4")

    # 2. Check filesystem by video_id naming convention
    video_dir = os.path.join(settings.cache_dir, "videos")
    path = os.path.join(video_dir, f"slideshow_{video_id}.mp4")
    if os.path.isfile(path):
        # Backfill SQLite
        await chat_store.set_slideshow_path(video_id, path)
        return FileResponse(path, media_type="video/mp4", filename="slideshow.mp4")

    # 3. Check old hash-based filenames
    if os.path.isdir(video_dir):
        for url_pattern in [
            f"https://www.youtube.com/watch?v={video_id}",
            f"https://youtu.be/{video_id}",
        ]:
            url_hash = hashlib.sha256(url_pattern.encode()).hexdigest()[:12]
            old_path = os.path.join(video_dir, f"slideshow_{url_hash}.mp4")
            if os.path.isfile(old_path):
                await chat_store.set_slideshow_path(video_id, old_path)
                return FileResponse(old_path, media_type="video/mp4", filename="slideshow.mp4")

    raise HTTPException(status_code=404, detail="No slideshow found for this video")


@router.get("/videos/{video_id}")
async def get_video_info(video_id: str):
    """Get a single video's info including slideshow and pipeline status."""
    video = await chat_store.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    has_slideshow = bool(video.get("slideshow_path") and os.path.isfile(video["slideshow_path"]))
    job_id = video.get("pipeline_job_id")
    pipeline_status = None
    pipeline_progress = None
    if job_id and job_id in jobs:
        pipeline_status = jobs[job_id]["status"]
        pipeline_progress = jobs[job_id]["progress"]
    return {
        "video_id": video["video_id"],
        "title": video["title"],
        "has_slideshow": has_slideshow,
        "slideshow_url": f"/api/slideshow/video/{video_id}" if has_slideshow else None,
        "pipeline_job_id": job_id,
        "pipeline_status": pipeline_status,
        "pipeline_progress": pipeline_progress,
    }


@router.get("/videos")
async def list_videos():
    """List all ingested videos with metadata and slideshow status."""
    videos = await chat_store.list_videos()
    result = []
    for v in videos:
        has_slideshow = bool(v.get("slideshow_path") and os.path.isfile(v["slideshow_path"]))
        result.append({
            "video_id": v["video_id"],
            "youtube_url": v["youtube_url"],
            "title": v["title"],
            "channel": v["channel"],
            "duration": v["duration"],
            "thumbnail": v["thumbnail"],
            "chunk_count": v["chunk_count"],
            "has_slideshow": has_slideshow,
            "slideshow_url": f"/api/slideshow/video/{v['video_id']}" if has_slideshow else None,
            "ingested_at": v["ingested_at"],
        })
    return result
