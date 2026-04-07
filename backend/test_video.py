"""Standalone test for the video generator agent."""
import asyncio
from dotenv import load_dotenv

load_dotenv()

from app.agents.video_generator import generate_videos

# Fake state with a sample script
test_state = {
    "youtube_url": "https://www.youtube.com/watch?v=test",
    "transcript_chunks": [],
    "top_concepts": [],
    "scripts": [
        {
            "concept_title": "Attention Mechanism in Transformers",
            "script_text": (
                "The attention mechanism allows a model to focus on relevant parts "
                "of the input sequence. Instead of processing tokens in order, "
                "attention computes weighted relationships between all tokens "
                "simultaneously, enabling the model to capture long-range dependencies."
            ),
            "segments_used": [],
        }
    ],
    "citations": [],
    "video_urls": [],
    "status": "processing",
    "error_message": "",
}


async def main():
    print("Starting video generation pipeline...")
    print(f"Concept: {test_state['scripts'][0]['concept_title']}")
    print()

    result = await generate_videos(test_state)

    print(f"Status: {result.get('status')}")
    if result.get("error_message"):
        print(f"Error: {result['error_message']}")

    for video in result.get("video_urls", []):
        print(f"\n--- {video.get('concept_title')} ---")
        print(f"  Infographic:          {video.get('infographic_url')}")
        print(f"  Explainer video:      {video.get('video_url')}")
        print(f"  Animated infographic: {video.get('animated_infographic_url')}")


if __name__ == "__main__":
    asyncio.run(main())
