"""
Tender - 配置管理
"""
import os, sys
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# 项目根目录：dev 时用 __file__ 向上找，打包时用 exe 所在目录
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys.executable).parent
else:
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
    SECRET_KEY: str = "tender-secret-key-change-in-production"
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
    EMBED_PROVIDER: str = "mock"  # dashscope | bge | m3e | mock
    DASHSCOPE_EMBED_MODEL: str = "text-embedding-v3"
    BGE_MODEL_PATH: str = ""
    M3E_MODEL_PATH: str = "moka-ai/m3e-base"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(DATA_DIR / "chromadb")

    # File size limit (MB)
    MAX_FILE_SIZE: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def update_env(key: str, value: str):
    """更新 .env 文件中的配置项"""
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # 清除缓存，下次 get_settings() 会重新读取
    get_settings.cache_clear()
