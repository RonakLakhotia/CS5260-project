from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    replicate_api_token: str = ""
    max_cost_per_session_sgd: float = 8.0
    cache_dir: str = "./cache"
    chroma_persist_dir: str = "./chroma_db"
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o"
    chunk_size: int = 1500
    chunk_overlap: int = 200
    max_transcript_tokens: int = 100000
    chat_db_path: str = "./chat.db"
    chat_history_token_budget: int = 50000
    cors_origins: str = "*"  # comma-separated origins, or "*" for all
    gemini_api_key: str = ""
    api_key: str = ""  # if set, all /api/* requests require X-API-Key header

    model_config = {"env_file": ".env"}


settings = Settings()
