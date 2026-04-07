"""Video generator agent — creates infographic slideshow using Nano Banana Pro.

Uses Google's Nano Banana Pro (via Replicate) for infographic generation
and ffmpeg for stitching slides into a video.
"""
import os
import asyncio
import hashlib
import subprocess
import tempfile
import urllib.request

import replicate

from app.models import YTSageState
from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("agent.video_generator")

RETRY_DELAY = 15
MAX_RETRIES = 3

IMAGE_MODEL = "google/nano-banana-pro"
SECONDS_PER_SLIDE = 5
MAX_CONCEPTS = 3


def _get_infographic_prompts(script: dict) -> list[str]:
    """Get 2 infographic prompts from script writer output, or generate fallbacks."""
    title = script.get("concept_title", "")

    prompt_1 = script.get("infographic_prompt_1") or (
        f"Educational infographic about '{title}'. "
        f"Clean modern design, 9:16 vertical format. "
        f"Title at top, key points with icons below. "
        f"Professional typography, blue and white color scheme."
    )

    prompt_2 = script.get("infographic_prompt_2") or (
        f"Educational diagram explaining how '{title}' works. "
        f"9:16 vertical format. Include labeled diagram with arrows. "
        f"Clean modern design, professional typography."
    )

    return [prompt_1, prompt_2]


async def _run_with_retry(model: str, input_params: dict, label: str) -> object | None:
    """Run a Replicate model with retry logic for rate limits."""
    for attempt in range(MAX_RETRIES):
        try:
            output = replicate.run(model, input=input_params)
            return output
        except Exception as e:
            if "429" in str(e) and attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  Rate limited on {label}, retrying in {wait}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(wait)
            else:
                print(f"  {label} failed: {e}")
                return None
    return None


async def _generate_infographic(prompt: str, label: str) -> str | None:
    """Generate an infographic image using Nano Banana Pro. Returns image URL."""
    output = await _run_with_retry(
        IMAGE_MODEL,
        {
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "output_format": "png",
        },
        label,
    )
    if output:
        # Nano Banana Pro returns a single FileOutput URL
        return str(output)
    return None


def _download_image(url: str, dest_path: str) -> bool:
    """Download an image from URL to local path."""
    try:
        urllib.request.urlretrieve(url, dest_path)
        return True
    except Exception as e:
        print(f"  Failed to download {url}: {e}")
        return False


def _stitch_slideshow(image_paths: list[str], output_path: str) -> bool:
    """Stitch images into an MP4 slideshow using ffmpeg."""
    if not image_paths:
        return False

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for img_path in image_paths:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {SECONDS_PER_SLIDE}\n")
        f.write(f"file '{image_paths[-1]}'\n")
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "24",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"  ffmpeg error: {result.stderr[:300]}")
            return False
        return True
    except Exception as e:
        print(f"  ffmpeg failed: {e}")
        return False
    finally:
        os.unlink(concat_file)


async def generate_videos(state: YTSageState) -> dict:
    """Generate infographic slideshow for concepts.

    For each concept:
    1. Generate 2 infographic images using Nano Banana Pro
    2. Stitch all into a single MP4 slideshow using ffmpeg
    """
    scripts = state.get("scripts", [])

    if not scripts:
        return {"video_urls": [], "status": "complete"}

    if not settings.replicate_api_token:
        return {
            "video_urls": [],
            "status": "complete",
            "error_message": "REPLICATE_API_TOKEN not set — skipping video generation",
        }

    os.environ["REPLICATE_API_TOKEN"] = settings.replicate_api_token

    output_dir = os.path.join(settings.cache_dir, "videos")
    os.makedirs(output_dir, exist_ok=True)

    video_results = []
    all_infographic_urls = []

    for script in scripts[:MAX_CONCEPTS]:
        concept_title = script.get("concept_title", "")
        print(f"  Processing '{concept_title}'...")

        prompts = _get_infographic_prompts(script)
        concept_urls = []

        for i, prompt in enumerate(prompts):
            print(f"    Generating infographic {i + 1}/2...")
            url = await _generate_infographic(prompt, f"Infographic {i + 1}: {concept_title}")
            if url:
                concept_urls.append(url)
            await asyncio.sleep(RETRY_DELAY)

        video_results.append({
            "concept_title": concept_title,
            "infographic_urls": concept_urls,
        })
        all_infographic_urls.extend(concept_urls)

    # Stitch all infographics into one slideshow
    slideshow_path = None
    if all_infographic_urls:
        print(f"  Stitching {len(all_infographic_urls)} infographics into slideshow...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths = []
            for i, url in enumerate(all_infographic_urls):
                img_path = os.path.join(tmp_dir, f"slide_{i:03d}.png")
                if _download_image(url, img_path):
                    image_paths.append(img_path)

            if image_paths:
                url_hash = hashlib.sha256(state.get("youtube_url", "").encode()).hexdigest()[:12]
                slideshow_path = os.path.join(output_dir, f"slideshow_{url_hash}.mp4")

                if _stitch_slideshow(image_paths, slideshow_path):
                    print(f"  Slideshow saved to {slideshow_path}")
                else:
                    print(f"  Slideshow stitching failed")
                    slideshow_path = None

    return {
        "video_urls": video_results,
        "slideshow_path": slideshow_path,
        "status": "complete",
    }
