"""
ClawOS X - FastAPI 入口
"""
import sys, os, time
from pathlib import Path

# 确保项目根目录在 Python 路径中（支持从 server/ 目录运行）
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# PyInstaller 打包后切到 exe 所在目录，确保 .env 和 data 路径正确
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.chdir(Path(sys.executable).parent)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import threading

from server.db.sqlite import init_db
from server.api import auth, kb, rag, bid, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# PyInstaller 打包后的资源路径
def _get_resource_path(relative_path: str) -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative_path
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
app.include_router(admin.router)

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


# SPA fallback: 处理所有非 API 路由
# 静态资源（/assets/...）也走这里，避免被 mounted handler 拦截
@app.get("/{path:path}")
async def spa_fallback(path: str):
    if not WEB_DIST.exists():
        return {"error": "not found"}
    # 静态资源直接返回
    asset_path = WEB_DIST / path
    if asset_path.exists() and asset_path.is_file():
        return FileResponse(str(asset_path))
    # 前端路由（/settings, /dashboard 等）返回 index.html
    return FileResponse(str(WEB_DIST / "index.html"))


# ---------------------------------------------------------------------------
# uvicorn 服务线程管理
# ---------------------------------------------------------------------------
_server_thread = None
_server_stop_event = None


def _run_server():
    """在线程中运行 uvicorn（等待停止信号）"""
    import uvicorn
    from server.config import get_settings
    settings = get_settings()
    config = uvicorn.Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    _server_stop_event.set()
    # uvicorn.run() 是阻塞的，直到 stop() 被调用
    import asyncio
    asyncio.run(server.serve())


def _start_server_thread():
    global _server_thread, _server_stop_event
    _server_stop_event = threading.Event()
    _server_thread = threading.Thread(target=_run_server, daemon=True)
    _server_thread.start()
    # 等待服务器真正启动
    time.sleep(1.5)


def _tray_restart_callback(stop=False):
    if stop:
        os._exit(0)
    # 重启：先启动新进程，再退出当前
    import subprocess, sys
    try:
        # DETACHED_PROCESS 让新进程完全独立，不继承控制台
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1  # SW_SHOWNORMAL
        subprocess.Popen([sys.executable], cwd=os.getcwd(),
                         startupinfo=si, creationflags=subprocess.DETACHED_PROCESS)
    except Exception:
        pass
    os._exit(0)


def _setup_tray():
    from server.core.tray import setup_tray
    setup_tray(_tray_restart_callback)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _start_server_thread()
    _setup_tray()

    # 保持主线程活跃（托盘在后台运行）
    while True:
        time.sleep(86400)
