from pydantic import BaseModel


# --- Stateless chat (legacy) ---

class ChatRequest(BaseModel):
    youtube_url: str
    question: str


class SourceChunk(BaseModel):
    text: str
    start_time: float
    end_time: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]


# --- Session-based chat ---

class CreateSessionRequest(BaseModel):
    youtube_url: str


class CreateSessionResponse(BaseModel):
    chat_id: str
    video_id: str


class SendMessageRequest(BaseModel):
    question: str


class SendMessageResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]


class MessageRecord(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class SessionRecord(BaseModel):
    chat_id: str
    video_id: str
    youtube_url: str
    created_at: str
