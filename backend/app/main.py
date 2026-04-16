from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routes import router
from app.services.chat_store import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="YTSage",
    description="YouTube to Shorts Synthesis Agent",
    lifespan=lifespan,
)

origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "x-api-key", "X-API-Key", "content-type", "Content-Type"],
    expose_headers=["*"],
)


@app.middleware("http")
async def api_key_check(request: Request, call_next):
    """If API_KEY is set, require X-API-Key header on /api/* routes."""
    if settings.api_key and request.url.path.startswith("/api/"):
        # Preflight OPTIONS requests skip auth (browsers don't send custom headers on them)
        if request.method != "OPTIONS":
            client_key = request.headers.get("x-api-key", "")
            if client_key != settings.api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
    return await call_next(request)


app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
