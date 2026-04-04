from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import PLANNER_SYSTEM_PROMPT
from app.models import YTSageState
from app.services.vector_store import query_chunks
from app.services.summary import parse_json_response

log = get_logger("agent.planner")


async def plan_concepts(state: YTSageState) -> dict:
    """Identify and rank top 3 concepts from the transcript using RAG."""
    video_id = state["video_id"]
    log.info("Planner started for video %s", video_id)

    overview_chunks = query_chunks(
        video_id,
        "main topics key concepts ideas discussed explained",
        n_results=15,
    )
    log.info("Retrieved %d overview chunks", len(overview_chunks))

    overview_chunks.sort(key=lambda c: c["chunk_index"])

    context = "\n\n".join(
        f"[{c['start_time']:.0f}s - {c['end_time']:.0f}s]: {c['text']}"
        for c in overview_chunks
    )

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )

    log.info("Calling %s to rank concepts...", settings.llm_model)
    response = await llm.ainvoke([
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Analyze the following transcript excerpts from a YouTube video and "
            f"identify the top 3 most important concepts.\n\nTranscript:\n{context}"
        )},
    ])

    parsed = parse_json_response(response.content)
    concepts = parsed.get("concepts", [])

    if not concepts:
        log.error("Failed to parse planner response: %s", response.content[:200])
        return {
            "top_concepts": [],
            "status": "error",
            "error_message": "Failed to parse planner response",
        }

    log.info("Planner identified %d concepts: %s", len(concepts), [c["title"] for c in concepts])
    return {
        "top_concepts": concepts,
        "status": "processing",
    }
