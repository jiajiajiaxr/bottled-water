from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agents, artifacts, auth, context, conversations, deployments, files, knowledge, logs, mcp, messages, models, sandbox, security_ops, skills, tasks, tools, websocket, workspaces
from app.core.config import get_settings
from app.core.errors import AppError
from db.session import AsyncSessionLocal
from app.core.logging_config import configure_logging
from app.core.response import fail, ok
from app.services.seed import ensure_seed_data


configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncSessionLocal() as db:
        try:
            await ensure_seed_data(db)
        except Exception:
            await db.rollback()
        yield


app = FastAPI(title="AgentHub API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=fail(exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=fail(1002, "参数校验失败", {"errors": exc.errors()}),
    )


@app.get("/api/v1/health")
async def health():
    return ok({"status": "ok", "provider": "mock" if settings.use_mock_llm else "ark"})


@app.get("/health")
async def root_health():
    return {"status": "ok", "provider": "mock" if settings.use_mock_llm else "ark"}


for router in [
    auth.router,
    agents.router,
    conversations.router,
    messages.router,
    tasks.router,
    artifacts.router,
    deployments.router,
    files.router,
    knowledge.router,
    models.router,
    mcp.router,
    skills.router,
    tools.router,
    sandbox.router,
    workspaces.router,
    security_ops.router,
    context.router,
    logs.router,
]:
    app.include_router(router, prefix=settings.api_prefix)

for router in [
    auth.compat_router,
    conversations.compat_router,
    messages.compat_router,
    tasks.compat_router,
    artifacts.compat_router,
    deployments.compat_router,
]:
    app.include_router(router)

app.include_router(websocket.router)
