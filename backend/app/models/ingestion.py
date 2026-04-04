import json

from pydantic import BaseModel, field_validator


class VideoMetadata(BaseModel):
    title: str = ""
    channel: str = ""
    uploader: str = ""
    upload_date: str = ""
    description: str = ""
    duration: int = 0
    language: str = ""
    view_count: int = 0
    like_count: int = 0
    tags: list[str] = []
    categories: list[str] = []
    thumbnail: str = ""
    summary: dict = {}  # Structured summary object

    @field_validator("summary", mode="before")
    @classmethod
    def parse_summary(cls, v):
        if isinstance(v, str):
            if not v:
                return {}
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {"raw": v}
        return v if isinstance(v, dict) else {}


class IngestionStatus(BaseModel):
    video_id: str
    status: str  # processing | complete | error
    progress: str
    chunk_count: int | None = None
    chat_id: str | None = None
    metadata: VideoMetadata | None = None
