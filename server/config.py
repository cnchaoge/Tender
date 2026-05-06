"""
ClawOS X - 配置管理
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UPLOADS_DIR = DATA_DIR / "uploads"
CHUNKS_DIR = DATA_DIR / "chunks"
GENERATED_DIR = DATA_DIR / "generated"
UPLOADS_DIR.mkdir(exist_ok=True)
CHUNKS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """应用配置"""

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = "clawosx-secret-key-change-in-production"
    DEBUG: bool = True

    # JWT
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时

    # AI Model
    LLM_PROVIDER: str = "dashscope"  # dashscope | openai | minimax | deepseek
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen-turbo"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    MINIMAX_API_KEY: str = ""
    MINIMAX_MODEL: str = "MiniMax-Text-01"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Embedding
    EMBED_PROVIDER: str = "dashscope"  # dashscope | bge
    DASHSCOPE_EMBED_MODEL: str = "text-embedding-v3"
    BGE_MODEL_PATH: str = ""

    # 向量数据库
    CHROMA_PERSIST_DIR: str = str(DATA_DIR / "chromadb")

    # 飞书
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_BOT_TOKEN: str = ""

    # 文件大小限制（MB）
    MAX_FILE_SIZE: int = 50

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache
def get_settings() -> Settings:
    return Settings()
