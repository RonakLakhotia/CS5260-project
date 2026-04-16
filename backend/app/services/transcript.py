import os
import tempfile

from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("transcript")

_yt_api = YouTubeTranscriptApi()


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    raise ValueError(f"Could not extract video ID from: {url}")


def _fetch_captions(video_id: str) -> list[dict] | None:
    """Try to get captions via YouTube Transcript API (v1.x).

    Priority: English (manual/auto) -> translated to English -> any language raw.
    Returns None if no captions are available at all.
    """
    try:
        transcript_list = _yt_api.list(video_id)
    except Exception:
        log.warning("No transcript list available for %s", video_id)
        return None

    transcripts = list(transcript_list)
    if not transcripts:
        log.warning("Empty transcript list for %s", video_id)
        return None

    # 1. Try English captions (manual or auto-generated)
    try:
        log.info("Trying English captions for %s", video_id)
        fetched = _yt_api.fetch(video_id, languages=["en"])
        chunks = [
            {"text": s.text, "start_time": s.start, "end_time": s.start + s.duration}
            for s in fetched.snippets
        ]
        log.info("Found English captions (%d entries)", len(chunks))
        return chunks
    except Exception:
        pass

    # 2. Try translating any available transcript to English
    for t in transcripts:
        if t.is_translatable:
            try:
                log.info("Trying %s -> English translation for %s", t.language_code, video_id)
                translated = t.translate("en").fetch()
                chunks = [
                    {"text": s.text, "start_time": s.start, "end_time": s.start + s.duration}
                    for s in translated.snippets
                ]
                log.info("Got translated captions (%d entries)", len(chunks))
                return chunks
            except Exception:
                log.warning("Translation from %s failed for %s", t.language_code, video_id)
                continue

    # 3. Fetch raw captions in whatever language is available
    for t in transcripts:
        try:
            log.info("Fetching raw %s captions for %s", t.language_code, video_id)
            fetched = _yt_api.fetch(video_id, languages=[t.language_code])
            chunks = [
                {"text": s.text, "start_time": s.start, "end_time": s.start + s.duration}
                for s in fetched.snippets
            ]
            log.info("Got raw %s captions (%d entries)", t.language_code, len(chunks))
            return chunks
        except Exception:
            log.warning("Failed to fetch %s captions for %s", t.language_code, video_id)
            continue

    log.warning("All caption fetch attempts failed for %s", video_id)
    return None


def _whisper_transcribe(youtube_url: str) -> list[dict]:
    """Download audio with yt-dlp and transcribe with OpenAI Whisper API."""
    import yt_dlp

    log.info("Falling back to Whisper transcription for %s", youtube_url)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]/best",
            "outtmpl": audio_path,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            # Use multiple YouTube clients to bypass format restrictions on server IPs
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "web"],
                }
            },
        }
        # Use cookies file if present (helps bypass YouTube bot detection on cloud IPs)
        _cookies = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cookies.txt")
        if os.path.isfile(_cookies):
            ydl_opts["cookiefile"] = _cookies

        log.info("Downloading audio via yt-dlp...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        actual_path = audio_path
        if not os.path.exists(actual_path):
            for f in os.listdir(tmpdir):
                if f.startswith("audio"):
                    actual_path = os.path.join(tmpdir, f)
                    break

        file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
        log.info("Audio downloaded (%.1f MB), sending to Whisper API...", file_size_mb)

        client = OpenAI(api_key=settings.openai_api_key)
        with open(actual_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

    chunks = []
    for segment in result.segments:
        chunks.append({
            "text": segment.text.strip(),
            "start_time": segment.start,
            "end_time": segment.end,
        })

    log.info("Whisper transcription complete: %d segments", len(chunks))
    return chunks


def get_transcript(youtube_url: str) -> list[dict]:
    """Fetch transcript with fallback chain:
    1. English captions (manual/auto)
    2. Any language -> English translation
    3. Raw captions in any available language
    4. Whisper transcription (download audio + OpenAI API)
    """
    video_id = extract_video_id(youtube_url)
    log.info("Fetching transcript for video %s", video_id)

    captions = _fetch_captions(video_id)
    if captions is not None:
        log.info("Caption fetch complete: %d raw chunks", len(captions))
        return captions

    return _whisper_transcribe(youtube_url)


def merge_chunks(chunks: list[dict], max_duration: float = 60.0) -> list[dict]:
    """Merge small transcript chunks into larger segments (~60s each)."""
    if not chunks:
        return []

    merged = []
    current = {
        "text": chunks[0]["text"],
        "start_time": chunks[0]["start_time"],
        "end_time": chunks[0]["end_time"],
    }

    for chunk in chunks[1:]:
        if chunk["end_time"] - current["start_time"] <= max_duration:
            current["text"] += " " + chunk["text"]
            current["end_time"] = chunk["end_time"]
        else:
            merged.append(current)
            current = {
                "text": chunk["text"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
            }

    merged.append(current)
    return merged


def semantic_chunk_transcript(
    raw_chunks: list[dict],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """Split transcript into semantic chunks with timestamp metadata."""
    if not raw_chunks:
        return []

    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    log.info("Semantic chunking: %d raw chunks (size=%d, overlap=%d)", len(raw_chunks), chunk_size, chunk_overlap)

    blocks = merge_chunks(raw_chunks, max_duration=15.0)
    log.info("Merged into %d timed blocks (~15s each)", len(blocks))

    block_offsets: list[dict] = []
    full_text = ""
    for block in blocks:
        start_char = len(full_text)
        full_text += block["text"] + " "
        end_char = len(full_text)
        block_offsets.append({
            "start_char": start_char,
            "end_char": end_char,
            "start_time": block["start_time"],
            "end_time": block["end_time"],
        })

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", ", ", " ", ""],
    )
    text_chunks = splitter.split_text(full_text)

    result = []
    search_start = 0
    for idx, chunk_text in enumerate(text_chunks):
        pos = full_text.find(chunk_text, search_start)
        if pos == -1:
            pos = full_text.find(chunk_text)
        if pos == -1:
            continue
        search_start = pos + 1

        chunk_start = pos
        chunk_end = pos + len(chunk_text)

        start_time = None
        end_time = None
        for bo in block_offsets:
            if bo["end_char"] > chunk_start and bo["start_char"] < chunk_end:
                if start_time is None or bo["start_time"] < start_time:
                    start_time = bo["start_time"]
                if end_time is None or bo["end_time"] > end_time:
                    end_time = bo["end_time"]

        if start_time is not None:
            result.append({
                "text": chunk_text.strip(),
                "start_time": start_time,
                "end_time": end_time,
                "chunk_index": idx,
            })

    log.info("Semantic chunking complete: %d chunks produced", len(result))
    return result
