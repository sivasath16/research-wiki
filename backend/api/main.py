from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from core.config import settings
from api.routes import auth, repos, wiki, jobs, chat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.session import init_db
    init_db()
    logger.info("Database tables initialized")
    yield


app = FastAPI(
    title="ResearchWiki API",
    description="DeepWiki-style research tool for GitHub repos",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Cookie", "Authorization"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
app.include_router(wiki.router, prefix="/api/wiki", tags=["wiki"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(chat.router, prefix="/ws", tags=["chat"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
