import json

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger
from app.models import YTSageState

log = get_logger("agent.script_writer")


async def write_scripts(state: YTSageState) -> dict:
    """Design infographic slides for the top concepts using GPT-4o via Replicate."""
    top_concepts = state.get("top_concepts", [])
    transcript_chunks = state.get("transcript_chunks", [])

    if not top_concepts:
        return {
            "scripts": [],
            "status": "error",
            "error_message": "No concepts available for script writing",
        }

    log.info("Script writer started for %d concepts", len(top_concepts[:3]))

    # Build per-concept context from planner segments instead of full transcript
    concepts_text_parts = []
    for i, c in enumerate(top_concepts[:3]):
        segments = c.get("segments", [])
        segment_text = "\n".join(
            f"  [{s['start_time']:.0f}s - {s['end_time']:.0f}s] {s['text']}"
            for s in segments
        )
        if not segment_text:
            # Fallback: use full transcript if no segments available
            segment_text = "\n".join(
                f"  [{chunk['start_time']:.0f}s - {chunk['end_time']:.0f}s] {chunk['text']}"
                for chunk in transcript_chunks
            )
            if len(segment_text) > 5000:
                segment_text = segment_text[:5000]

        concepts_text_parts.append(
            f"{i+1}. {c['title']} ({c.get('start_time', 0):.0f}s - {c.get('end_time', 0):.0f}s): {c.get('description', '')}\n"
            f"   Relevant transcript:\n{segment_text}"
        )

    concepts_text = "\n\n".join(concepts_text_parts)

    user_prompt = f"""Given a YouTube video transcript and a list of key concepts, design 2 infographic slides per concept.

For each concept, provide:
1. "concept_title": The concept title
2. "infographic_prompt_1": A detailed prompt for generating the FIRST educational infographic image. This should be an overview/introduction slide — include the concept title, a brief definition, and 2-3 key points with icons. Describe layout, colors, and typography.
3. "infographic_prompt_2": A detailed prompt for generating the SECOND educational infographic image. This should be a deeper dive — include a diagram, example, or visual explanation of how the concept works. Different layout from slide 1.

Both infographic prompts should specify: 9:16 vertical format, clean modern design, professional typography. Be specific about what text should appear on each slide.

Return ONLY a JSON array with objects containing these 3 fields. No other text.

Concepts to write about (with relevant transcript segments):
{concepts_text}"""

    try:
        log.info("Calling %s via OpenAI for infographic prompts...", settings.llm_model)
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0.4,
            max_tokens=2000,
        )
        response = await llm.ainvoke([
            {"role": "system", "content": "You are an educational content writer. Return only valid JSON."},
            {"role": "user", "content": user_prompt},
        ])

        response_text = response.content

        start_idx = response_text.find("[")
        end_idx = response_text.rfind("]") + 1

        if start_idx == -1 or end_idx == 0:
            log.error("Could not find JSON in script writer response: %s", response_text[:500])
            return {
                "scripts": [],
                "status": "error",
                "error_message": "Failed to parse script writer response",
            }

        scripts = json.loads(response_text[start_idx:end_idx])

        log.info("Script writer produced %d infographic plans: %s",
                 len(scripts), [s.get("concept_title", "") for s in scripts])
        return {
            "scripts": scripts,
            "status": "processing",
        }

    except Exception as e:
        log.error("Script writer failed: %s", e)
        return {
            "scripts": [],
            "status": "error",
            "error_message": f"Script writer failed: {str(e)}",
        }
