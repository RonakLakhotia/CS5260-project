import os
import json
import replicate

from app.core.config import settings
from app.core.logger import get_logger
from app.models import YTSageState
from app.services.vector_store import query_chunks

log = get_logger("agent.planner")

LLM_MODEL = "openai/gpt-4o"


async def plan_concepts(state: YTSageState) -> dict:
    """Identify and rank top 3 concepts from the transcript using GPT-4o via Replicate."""
    video_id = state.get("video_id", "")
    log.info("Planner started for video %s", video_id)

    # Use RAG to get overview chunks if vector store is available
    try:
        overview_chunks = query_chunks(
            video_id,
            "main topics key concepts ideas discussed explained",
            n_results=15,
        )
        overview_chunks.sort(key=lambda c: c["chunk_index"])
        log.info("Retrieved %d overview chunks from vector store", len(overview_chunks))

        context = "\n".join(
            f"[{c['start_time']:.0f}s - {c['end_time']:.0f}s] {c['text']}"
            for c in overview_chunks
        )
    except Exception:
        # Fallback: use transcript_chunks directly
        log.warning("Vector store unavailable, using raw transcript chunks")
        transcript_chunks = state.get("transcript_chunks", [])
        if not transcript_chunks:
            return {
                "top_concepts": [],
                "status": "error",
                "error_message": "No transcript chunks available",
            }
        context = "\n".join(
            f"[{chunk['start_time']:.0f}s - {chunk['end_time']:.0f}s] {chunk['text']}"
            for chunk in transcript_chunks
        )

    if len(context) > 30000:
        context = context[:30000]

    os.environ["REPLICATE_API_TOKEN"] = settings.replicate_api_token

    prompt = f"""You are an educational content analyst. Given a YouTube video transcript, identify the top 3 most important concepts or topics discussed.

For each concept, provide:
1. A clear, concise title (5-8 words)
2. A brief description of why this concept is important (1-2 sentences)
3. The approximate start and end timestamps (in seconds) where this concept is primarily discussed
4. A visual scene description that could be used to generate an abstract animation representing this concept (describe colors, shapes, motion — no text)

Return your response as a JSON array with exactly 3 objects. Each object must have these fields:
- "title": string
- "description": string
- "start_time": number (seconds)
- "end_time": number (seconds)
- "visual_description": string

Return ONLY the JSON array, no other text.

Transcript:
{context}"""

    try:
        log.info("Calling GPT-4o via Replicate to rank concepts...")
        output = replicate.run(
            LLM_MODEL,
            input={
                "prompt": prompt,
                "system_prompt": "You are an educational content analyst. Return only valid JSON.",
                "max_completion_tokens": 1500,
                "temperature": 0.3,
            },
        )

        response_text = "".join(output)

        start_idx = response_text.find("[")
        end_idx = response_text.rfind("]") + 1

        if start_idx == -1 or end_idx == 0:
            log.error("Could not find JSON in planner response: %s", response_text[:500])
            return {
                "top_concepts": [],
                "status": "error",
                "error_message": "Failed to parse planner response",
            }

        concepts = json.loads(response_text[start_idx:end_idx])

        # Add rank and extract relevant transcript segments for each concept
        transcript_chunks = state.get("transcript_chunks", [])
        for i, concept in enumerate(concepts):
            concept["rank"] = i + 1
            c_start = concept.get("start_time", 0)
            c_end = concept.get("end_time", 0)
            concept["segments"] = [
                chunk for chunk in transcript_chunks
                if chunk["start_time"] < c_end and chunk["end_time"] > c_start
            ]

        log.info("Planner identified %d concepts: %s", len(concepts), [c["title"] for c in concepts])
        return {
            "top_concepts": concepts,
            "status": "processing",
        }

    except Exception as e:
        log.error("Planner agent failed: %s", e)
        return {
            "top_concepts": [],
            "status": "error",
            "error_message": f"Planner failed: {str(e)}",
        }
