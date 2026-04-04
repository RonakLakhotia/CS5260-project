from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import SCRIPT_WRITER_SYSTEM_PROMPT
from app.models import YTSageState
from app.services.vector_store import query_chunks

log = get_logger("agent.script_writer")


async def write_scripts(state: YTSageState) -> dict:
    """Write ~30-second narration scripts for the top 2 concepts using RAG."""
    video_id = state["video_id"]
    top_2 = state["top_concepts"][:2]
    log.info("Script writer started for video %s (%d concepts)", video_id, len(top_2))

    if not top_2:
        log.error("No concepts available to write scripts for")
        return {"scripts": [], "status": "error", "error_message": "No concepts to write scripts for"}

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )

    scripts = []
    for i, concept in enumerate(top_2):
        log.info("Writing script %d/%d: '%s'", i + 1, len(top_2), concept["title"])

        query = concept["title"]
        if concept.get("description"):
            query += " " + concept["description"]
        if concept.get("relevant_keywords"):
            query += " " + concept["relevant_keywords"]

        relevant = query_chunks(video_id, query, n_results=8)
        relevant.sort(key=lambda c: c["chunk_index"])

        context = "\n\n".join(
            f"[{c['start_time']:.0f}s - {c['end_time']:.0f}s]: {c['text']}"
            for c in relevant
        )

        response = await llm.ainvoke([
            {"role": "system", "content": SCRIPT_WRITER_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Write a 30-second narration script about: {concept['title']}\n\n"
                f"Description: {concept.get('description', '')}\n\n"
                f"Source material from the video:\n{context}"
            )},
        ])

        scripts.append({
            "concept_title": concept["title"],
            "script_text": response.content,
            "segments_used": [
                {"start_time": c["start_time"], "end_time": c["end_time"]}
                for c in relevant
            ],
        })
        log.info("Script for '%s' complete (%d words)", concept["title"], len(response.content.split()))

    log.info("Script writer finished: %d scripts produced", len(scripts))
    return {"scripts": scripts, "status": "processing"}
