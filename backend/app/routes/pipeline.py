import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from app.core.logger import get_logger
from app.models import (
    ProcessRequest,
    JobResponse,
    StatusResponse,
    ResultResponse,
)
from app.agents.graph import build_graph

log = get_logger("api.pipeline")
router = APIRouter(tags=["pipeline"])

# In-memory job store (swap for Redis/DB later if needed)
jobs: dict[str, dict] = {}

# Build the LangGraph pipeline once
pipeline = build_graph()


async def _run_pipeline(job_id: str, youtube_url: str):
    """Background coroutine that runs the full LangGraph pipeline."""
    try:
        jobs[job_id]["progress"] = "Ingesting transcript into vector DB"
        log.info("[pipeline:%s] Starting pipeline for %s", job_id[:8], youtube_url)

        initial_state = {
            "youtube_url": youtube_url,
            "video_id": "",
            "transcript_chunks": [],
            "top_concepts": [],
            "scripts": [],
            "citations": [],
            "video_urls": [],
            "status": "processing",
            "error_message": "",
        }

        result = await pipeline.ainvoke(initial_state)

        if result.get("error_message"):
            jobs[job_id]["status"] = "error"
            jobs[job_id]["progress"] = result["error_message"]
            log.error("[pipeline:%s] Pipeline error: %s", job_id[:8], result["error_message"])
            return

        concepts = []
        for i, script in enumerate(result.get("scripts", [])):
            if i < len(result.get("citations", [])):
                citation_data = result["citations"][i]
            else:
                log.warning("[pipeline:%s] Missing citations for script %d: '%s'", job_id[:8], i, script["concept_title"])
                citation_data = {"claims": []}
            concepts.append({
                "title": script["concept_title"],
                "script": script["script_text"],
                "citations": citation_data["claims"],
                "video_url": None,
            })

        third = None
        if len(result.get("top_concepts", [])) > 2:
            third = {
                "title": result["top_concepts"][2]["title"],
                "script": "",
                "citations": [],
                "video_url": None,
            }

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = "Done"
        jobs[job_id]["result"] = {"concepts": concepts, "third_concept": third}
        log.info("[pipeline:%s] Pipeline complete: %d concepts", job_id[:8], len(concepts))

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = f"Error: {str(e)}"
        log.error("[pipeline:%s] Pipeline failed: %s", job_id[:8], e, exc_info=True)


@router.post("/process", response_model=JobResponse)
async def process_video(request: ProcessRequest):
    """Submit a YouTube URL for full processing (ingest → plan → script → cite)."""
    job_id = str(uuid.uuid4())
    log.info("Process requested for %s → job %s", request.youtube_url, job_id[:8])
    jobs[job_id] = {
        "status": "processing",
        "progress": "Starting pipeline",
        "youtube_url": request.youtube_url,
        "result": None,
    }
    asyncio.create_task(_run_pipeline(job_id, request.youtube_url))
    return JobResponse(job_id=job_id)


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(status=job["status"], progress=job["progress"])


@router.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """Get completed job results."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Job not complete yet")
    return job["result"]


@router.post("/generate-third/{job_id}")
async def generate_third(job_id: str):
    """Generate video for the 3rd concept (on-demand)."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # TODO: trigger video generation for 3rd concept
    return {"video_url": None, "message": "Not implemented yet"}
