import json
import re

import tiktoken
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("summary")

MAX_TRANSCRIPT_TOKENS = 100_000

SYSTEM_PROMPT = """You are a skilled video summarizer. Given a video's metadata and full transcript with timestamps, produce a rich, human-readable summary that someone would genuinely enjoy reading — as if a smart friend watched the video and told you everything interesting about it.

Respond with ONLY valid JSON in this exact format:
{
  "overview": "A compelling 2-3 sentence hook that captures what this video is about and why it's interesting.",
  "detailed_summary": "A well-written 3-6 paragraph narrative summary of the video. Cover the key points, arguments, stories, and examples in the order they appear. Write in a natural, engaging style — not bullet points. Include specific details, names, numbers, and quotes from the video that make it informative. A reader should feel they understand the video's content without watching it.",
  "topics": [
    {
      "title": "Topic name",
      "timestamp": "MM:SS",
      "description": "2-3 sentence description of what is covered and why it matters"
    }
  ],
  "takeaways": [
    "Specific, actionable or insightful takeaway — not generic"
  ],
  "timeline": [
    {
      "timestamp": "MM:SS",
      "description": "What is being discussed at this point"
    }
  ]
}

Guidelines:
- The overview should hook the reader — make them curious, not just informed
- The detailed_summary is the most important field. Write it like a well-crafted article. Include specifics from the transcript: names, examples, anecdotes, data points. Avoid vague statements like "various topics were discussed"
- Identify 3-8 major topics with timestamps and meaningful descriptions
- List 3-5 takeaways that are specific to THIS video, not generic advice
- Timeline entries roughly every few minutes covering the full video
- Use MM:SS format (or H:MM:SS for videos over 1 hour)"""


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens using tiktoken."""
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or H:MM:SS."""
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def _format_transcript(raw_segments: list[dict]) -> str:
    """Join segments as [MM:SS] text lines."""
    lines = []
    for seg in raw_segments:
        ts = _format_timestamp(seg["start_time"])
        lines.append(f"[{ts}] {seg['text']}")
    return "\n".join(lines)


def _sample_long_transcript(raw_segments: list[dict], max_tokens: int) -> str:
    """Sample from a very long transcript: first 15%, middle 15%, last 15%, then fill uniformly."""
    n = len(raw_segments)
    chunk_size = max(1, int(n * 0.15))

    # Take beginning, middle, and end
    start = raw_segments[:chunk_size]
    mid_begin = max(0, n // 2 - chunk_size // 2)
    middle = raw_segments[mid_begin:mid_begin + chunk_size]
    end = raw_segments[-chunk_size:]

    # Collect selected indices
    selected_indices = set(range(chunk_size))
    selected_indices.update(range(mid_begin, mid_begin + chunk_size))
    selected_indices.update(range(n - chunk_size, n))

    # Uniformly sample from remaining
    remaining = [i for i in range(n) if i not in selected_indices]
    sampled = start + middle + end

    # Add more until we approach the token limit
    text = _format_transcript(sampled)
    token_count = count_tokens(text)

    if remaining and token_count < max_tokens:
        step = max(1, len(remaining) // ((max_tokens - token_count) // 50))
        for i in range(0, len(remaining), step):
            seg = raw_segments[remaining[i]]
            sampled.append(seg)
            token_count += count_tokens(f"[{_format_timestamp(seg['start_time'])}] {seg['text']}\n")
            if token_count >= max_tokens * 0.9:
                break

    # Sort by start_time to maintain chronological order
    sampled.sort(key=lambda s: s["start_time"])
    return _format_transcript(sampled)


def _parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("Failed to parse summary JSON, returning raw text")
        return {"raw": content}


async def generate_summary(raw_segments: list[dict], video_meta: dict) -> str:
    """Generate a structured summary of a video transcript.

    Returns a JSON string. On failure, returns '{}' — never blocks ingestion.
    """
    if not raw_segments:
        return "{}"

    try:
        # Format transcript
        full_text = _format_transcript(raw_segments)
        token_count = count_tokens(full_text)
        log.info("Transcript: %d tokens (%d segments)", token_count, len(raw_segments))

        if token_count <= MAX_TRANSCRIPT_TOKENS:
            transcript_text = full_text
            log.info("Full transcript within limit, sending directly to LLM")
        else:
            transcript_text = _sample_long_transcript(raw_segments, MAX_TRANSCRIPT_TOKENS)
            sampled_tokens = count_tokens(transcript_text)
            log.info("Transcript too long (%d tokens), sampled to %d tokens", token_count, sampled_tokens)
            transcript_text = (
                "Note: This is a sampled subset of a very long transcript. "
                "Timestamps are preserved.\n\n" + transcript_text
            )

        # Build metadata context
        meta_lines = []
        if video_meta.get("title"):
            meta_lines.append(f"Title: {video_meta['title']}")
        if video_meta.get("channel"):
            meta_lines.append(f"Channel: {video_meta['channel']}")
        if video_meta.get("duration"):
            meta_lines.append(f"Duration: {_format_timestamp(video_meta['duration'])}")
        meta_context = "\n".join(meta_lines)

        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )

        log.info("Calling %s for summary generation...", settings.llm_model)
        response = await llm.ainvoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"--- Video Info ---\n{meta_context}\n\n"
                f"--- Full Transcript ---\n{transcript_text}"
            )},
        ])

        summary = _parse_json_response(response.content)
        summary_json = json.dumps(summary, ensure_ascii=False)
        log.info("Summary generated: %d topics, %d takeaways",
                 len(summary.get("topics", [])), len(summary.get("takeaways", [])))
        return summary_json

    except Exception as e:
        log.error("Summary generation failed: %s", e)
        return "{}"
