from fastapi import APIRouter

from app.routes.ingestion import router as ingestion_router
from app.routes.pipeline import router as pipeline_router
from app.routes.chat import router as chat_router
from app.routes.debug import router as debug_router
from app.routes.chat_sessions import router as chat_sessions_router

router = APIRouter()
router.include_router(ingestion_router)
router.include_router(pipeline_router)
router.include_router(chat_router)
router.include_router(chat_sessions_router)
router.include_router(debug_router)
