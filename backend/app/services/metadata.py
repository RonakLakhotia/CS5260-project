import os

import yt_dlp

from app.core.logger import get_logger

log = get_logger("metadata")

# If a cookies.txt file exists next to the backend, use it for yt-dlp
# (helps avoid YouTube's "sign in to confirm you're not a bot" on cloud IPs)
_COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cookies.txt")


def _ydl_opts_base() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        },
    }
    if os.path.isfile(_COOKIES_FILE):
        opts["cookiefile"] = _COOKIES_FILE
    return opts


def fetch_video_metadata(youtube_url: str) -> dict:
    """Fetch video metadata via yt-dlp (no download)."""
    log.info("Fetching metadata for %s", youtube_url)

    ydl_opts = _ydl_opts_base()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

    # Reject live streams, premieres, and stations
    is_live = info.get("is_live", False)
    live_status = info.get("live_status", "")
    duration = info.get("duration")

    if is_live or live_status in ("is_live", "is_upcoming"):
        raise ValueError("Live streams and premieres are not supported. Please use a completed video.")

    if not duration or duration <= 0:
        raise ValueError("This video has no duration. It may be a live stream, station, or unavailable video.")

    metadata = {
        "title": info.get("title", ""),
        "channel": info.get("channel", ""),
        "uploader": info.get("uploader", ""),
        "upload_date": _format_date(info.get("upload_date")),
        "description": info.get("description", ""),
        "duration": duration,
        "language": info.get("language", ""),
        "view_count": info.get("view_count", 0),
        "like_count": info.get("like_count", 0),
        "tags": info.get("tags", []),
        "categories": info.get("categories", []),
        "thumbnail": info.get("thumbnail", ""),
    }

    log.info("Metadata fetched: '%s' by %s (%ds)", metadata["title"], metadata["channel"], metadata["duration"])
    return metadata


def _format_date(raw: str | None) -> str:
    """Convert yt-dlp date '20260331' → '2026-03-31'."""
    if not raw or len(raw) != 8:
        return raw or ""
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
