"""Step-by-step pipeline test. Run each step individually to debug."""
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from app.services.transcript import get_transcript, merge_chunks
from app.agents.planner import plan_concepts
from app.agents.script_writer import write_scripts
from app.agents.video_generator import generate_videos

# Change this to any YouTube video
YOUTUBE_URL = "https://www.youtube.com/watch?v=eMlx5fFNoYc"  # 3Blue1Brown attention


def save_state(state: dict, filename: str):
    """Save state to JSON for inspection between steps."""
    with open(f"test_output_{filename}.json", "w") as f:
        json.dump(state, f, indent=2)
    print(f"  → Saved to test_output_{filename}.json")


async def step1_transcript():
    """Step 1: Fetch and merge transcript."""
    print("\n=== STEP 1: Transcript ===")
    raw = get_transcript(YOUTUBE_URL)
    merged = merge_chunks(raw)
    print(f"  Raw chunks: {len(raw)}")
    print(f"  Merged chunks: {len(merged)}")
    print(f"  First chunk: {merged[0]['text'][:100]}...")

    state = {
        "youtube_url": YOUTUBE_URL,
        "transcript_chunks": merged,
        "top_concepts": [],
        "scripts": [],
        "citations": [],
        "video_urls": [],
        "status": "processing",
        "error_message": "",
    }
    save_state(state, "1_transcript")
    return state


async def step2_planner(state: dict):
    """Step 2: Identify top concepts."""
    print("\n=== STEP 2: Planner ===")
    result = await plan_concepts(state)
    state.update(result)

    if state["status"] == "error":
        print(f"  ERROR: {state['error_message']}")
        return state

    for c in state["top_concepts"]:
        print(f"  {c['rank']}. {c['title']}")
        print(f"     {c.get('description', '')[:80]}")

    save_state(state, "2_planner")
    return state


async def step3_script_writer(state: dict):
    """Step 3: Write scripts and prompts."""
    print("\n=== STEP 3: Script Writer ===")
    result = await write_scripts(state)
    state.update(result)

    if state["status"] == "error":
        print(f"  ERROR: {state['error_message']}")
        return state

    for s in state["scripts"]:
        print(f"  - {s['concept_title']}")
        print(f"    Script: {s.get('script_text', '')[:80]}...")
        print(f"    Infographic prompt: {s.get('infographic_prompt', '')[:60]}...")
        print(f"    Video prompt: {s.get('video_prompt', '')[:60]}...")

    save_state(state, "3_scripts")
    return state


async def step4_video_generator(state: dict):
    """Step 4: Generate infographics and slideshow."""
    print("\n=== STEP 4: Video Generator ===")
    print("  Generating infographics via Nano Banana Pro and stitching slideshow...")
    result = await generate_videos(state)
    state.update(result)

    for v in state.get("video_urls", []):
        print(f"\n  {v.get('concept_title')}:")
        for url in v.get("infographic_urls", []):
            print(f"    Infographic: {url}")

    if state.get("slideshow_path"):
        print(f"\n  Slideshow: {state['slideshow_path']}")

    save_state(state, "4_videos")
    return state


async def main():
    import sys
    steps = sys.argv[1] if len(sys.argv) > 1 else "1"

    state = None

    if "1" in steps:
        state = await step1_transcript()

    if "2" in steps:
        if not state:
            with open("test_output_1_transcript.json") as f:
                state = json.load(f)
        state = await step2_planner(state)

    if "3" in steps:
        if not state:
            with open("test_output_2_planner.json") as f:
                state = json.load(f)
        state = await step3_script_writer(state)

    if "4" in steps:
        if not state:
            with open("test_output_3_scripts.json") as f:
                state = json.load(f)
        state = await step4_video_generator(state)

    print("\nDone.")


if __name__ == "__main__":
    main = asyncio.run(main())
