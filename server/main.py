"""
ClawOS X - FastAPI 入口
"""
import sys, os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from server.db.sqlite import init_db
from server.api import auth, kb, rag, bid, feishu, admin, relay


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# PyInstaller 打包后的资源路径
def _get_resource_path(relative_path: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # onefile 模式：从 sys._MEIPASS 解压目录读取
        return Path(sys._MEIPASS) / relative_path
    # 开发模式：从项目根目录读取
    return Path(__file__).resolve().parent.parent / relative_path


app = FastAPI(title="ClawOS X", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(rag.router)
app.include_router(bid.router)
app.include_router(feishu.router)
app.include_router(admin.router)
app.include_router(relay.router)

# 静态文件（前端dist）
WEB_DIST = _get_resource_path("web/dist")
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")


@app.get("/")
async def root():
    if WEB_DIST.exists():
        return FileResponse(str(WEB_DIST / "index.html"))
    return {"message": "ClawOS X API", "version": "1.0.0", "error": "web dist not found"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from server.config import get_settings
    settings = get_settings()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

