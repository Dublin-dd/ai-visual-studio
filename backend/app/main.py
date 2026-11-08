from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .db import init_db
from .routers import agent, assets, drama, exports, projects, tasks
from .services import task_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task_runner.reset_running_tasks()

    # 启动时后台补下载：网络恢复后把已生成但没下下来的片段免费救回
    import threading

    threading.Thread(target=task_runner.resume_failed_downloads, daemon=True).start()

    task_runner.start_worker()
    try:
        yield
    finally:
        task_runner.stop_worker()


app = FastAPI(title="云端 AI 视觉创作工作台", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3010",
        "http://127.0.0.1:3010",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数校验失败"}},
    )


@app.exception_handler(Exception)
async def unhandled_exc_handler(request, exc):
    # 不把堆栈返回给客户端（底线 3）
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "服务内部错误"}},
    )


app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(tasks.router)
app.include_router(exports.router)
app.include_router(drama.router)
app.include_router(agent.router)


@app.get("/api/health")
def health():
    return {"ok": True, "worker_enabled": config.WORKER_ENABLED, "has_image_key": bool(config.IMAGE_API_KEY.strip())}
