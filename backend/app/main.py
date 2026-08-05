"""FastAPI 应用入口。

- CORS 配置
- 路由挂载（统一前缀 /api/v1）
- 启动时建表
- 统一异常处理
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db
from .routers import assets, conversations, providers, system, tasks, templates

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 统一异常处理：返回 {error: {code, message, detail}}
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": f"{type(exc).__name__}: {exc}",
                    "detail": "服务端内部错误，请查看日志",
                }
            },
        )

    # 路由挂载
    api_v1_prefix = "/api/v1"
    app.include_router(tasks.router, prefix=api_v1_prefix)
    app.include_router(assets.router, prefix=api_v1_prefix)
    app.include_router(providers.router, prefix=api_v1_prefix)
    app.include_router(conversations.router, prefix=api_v1_prefix)
    app.include_router(templates.router, prefix=api_v1_prefix)
    app.include_router(system.router, prefix=api_v1_prefix)

    @app.on_event("startup")
    def _on_startup() -> None:
        try:
            init_db()
            logger.info("Database initialized (WAL mode)")
        except Exception:
            logger.exception("Database init failed")

    @app.get("/")
    def root():
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/v1/system/health",
        }

    return app


app = create_app()
