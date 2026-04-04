from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.core.prompts import EXTRACT_CLAIMS_PROMPT
from app.models import YTSageState
from app.services.vector_store import query_chunks
from app.services.summary import parse_json_response

log = get_logger("agent.citation_mapper")


async def map_citations(state: YTSageState) -> dict:
    """Map each claim in the scripts to source timestamps using RAG."""
    video_id = state["video_id"]
    log.info("Citation mapper started for video %s (%d scripts)", video_id, len(state["scripts"]))

    if not state["scripts"]:
        log.warning("No scripts to map citations for")
        return {"citations": [], "status": "complete"}

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    citations = []
    for script in state["scripts"]:
        log.info("Extracting claims from script: '%s'", script["concept_title"])

        claim_response = await llm.ainvoke([
            {"role": "system", "content": EXTRACT_CLAIMS_PROMPT},
            {"role": "user", "content": script["script_text"]},
        ])

        parsed = parse_json_response(claim_response.content)
        # parse_json_response returns a dict; claims should be a list
        claims = parsed if isinstance(parsed, list) else parsed.get("raw", [])
        if not isinstance(claims, list):
            log.error("Failed to parse claims for '%s': %s", script["concept_title"], claim_response.content[:200])
            claims = []
        else:
            log.info("Extracted %d claims from '%s'", len(claims), script["concept_title"])

        mapped_claims = []
        for claim_text in claims:
            matches = query_chunks(video_id, claim_text, n_results=1)
            if matches:
                best = matches[0]
                timestamp = int(best["start_time"])
                mapped_claims.append({
                    "claim": claim_text,
                    "timestamp": timestamp,
                    "url": f"https://www.youtube.com/watch?v={video_id}&t={timestamp}",
                })
                log.info("  Claim mapped → %ds: %.60s...", timestamp, claim_text)

        citations.append({
            "concept_title": script["concept_title"],
            "claims": mapped_claims,
        })

    log.info("Citation mapping complete: %d scripts processed", len(citations))
    return {"citations": citations, "status": "complete"}
