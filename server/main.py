"""
ClawOS X - FastAPI 入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from server.db.sqlite import init_db
from server.api import auth, kb, rag, bid, feishu, admin, relay


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


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


@app.get("/")
def root():
    return {"message": "ClawOS X API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from server.config import get_settings
    settings = get_settings()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
