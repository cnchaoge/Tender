"""
Tender - 配置管理
"""
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# 项目根目录：dev 时用 __file__ 向上找，打包时用 exe 所在目录
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UPLOADS_DIR = DATA_DIR / "uploads"
CHUNKS_DIR = DATA_DIR / "chunks"
GENERATED_DIR = DATA_DIR / "generated"
UPLOADS_DIR.mkdir(exist_ok=True)
CHUNKS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

# Historical default shipped in the repo. Anyone who has read it can forge JWTs,
# so it is never accepted as a signing key.
PUBLIC_INSECURE_SECRET_KEYS = frozenset({
    "tender-secret-key-change-in-production",
})
DEV_SECRET_FILENAME = ".secret_key"
_MIN_DEV_SECRET_LENGTH = 32


class SecretKeyError(RuntimeError):
    """SECRET_KEY is missing or is a known public value."""


class Settings(BaseSettings):
    """应用配置"""

    # 服务。默认只绑定本机。办公室网络上不要改成 0.0.0.0 后直接暴露明文 HTTP。
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    # Empty means "not configured". Do not put a real or public secret here.
    SECRET_KEY: str = ""
    DEBUG: bool = True
    # production / prod requires an explicit SECRET_KEY even if DEBUG is true.
    APP_ENV: str = "development"

    # JWT
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时

    # AI Model
    LLM_PROVIDER: str = "ollama"  # ollama | dashscope | openai | minimax | deepseek
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen-turbo"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    MINIMAX_API_KEY: str = ""
    MINIMAX_MODEL: str = "MiniMax-Text-01"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Ollama (Local LLM)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_EMBED_MODEL: str = ""

    # Embedding
    EMBED_PROVIDER: str = "ollama"  # ollama | dashscope | bge | m3e | mock
    DASHSCOPE_EMBED_MODEL: str = "text-embedding-v3"
    BGE_MODEL_PATH: str = ""
    M3E_MODEL_PATH: str = "moka-ai/m3e-base"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(DATA_DIR / "chromadb")

    # 企业信息
    COMPANY_NAME: str = "投标单位名称"

    # File size limit (MB)
    MAX_FILE_SIZE: int = 50

    # Comma-separated directories folder import may copy from. Empty disables
    # folder scan. Home, ancestors of home, and filesystem roots are ignored.
    KB_SCAN_ROOTS: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


def is_production(settings: Settings) -> bool:
    """True when this process must not invent a JWT signing key."""
    env = (settings.APP_ENV or "").strip().lower()
    if env in {"prod", "production"}:
        return True
    return not bool(settings.DEBUG)


def write_private_text(path: Path, text: str) -> None:
    """Atomically write text so only the current user can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_dev_secret(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if len(value) < _MIN_DEV_SECRET_LENGTH or value in PUBLIC_INSECURE_SECRET_KEYS:
        return ""
    return value


def load_or_create_dev_secret(data_dir: Path) -> str:
    """Return the stable per-install dev secret, creating it on first use."""
    path = data_dir / DEV_SECRET_FILENAME
    existing = _read_dev_secret(path)
    if existing:
        return existing
    value = secrets.token_urlsafe(48)
    write_private_text(path, value + "\n")
    print(
        "[config] SECRET_KEY is not set. Generated a stable per-install JWT "
        f"secret at {path}. It is reused on later startups and is not written "
        "to .env. Set SECRET_KEY to override it."
    )
    return value


def resolve_secret_key(settings: Settings, data_dir: Path | None = None) -> str:
    """Return the JWT signing secret for this process.

    An explicit SECRET_KEY is used as-is. The historical public default is
    treated as unset. Production refuses to start until a unique key is
    configured. Local/dev stores a generated key under the data directory
    and reuses that file on later runs.
    """
    configured = (settings.SECRET_KEY or "").strip()
    if configured in PUBLIC_INSECURE_SECRET_KEYS:
        configured = ""
    if configured:
        return configured
    directory = DATA_DIR if data_dir is None else data_dir
    if is_production(settings):
        raise SecretKeyError(
            "Refusing to start: SECRET_KEY is not set to a unique value. "
            "Production mode (DEBUG=false or APP_ENV=production) will not "
            "sign JWTs with a generated or public secret. Set SECRET_KEY in "
            "the environment or .env. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))". '
            "The old default 'tender-secret-key-change-in-production' is "
            "public and is not accepted."
        )
    return load_or_create_dev_secret(directory)


@lru_cache
def get_settings() -> Settings:
    # Read the same .env file update_env() writes, independent of the process
    # cwd. _env_file is accepted at runtime; the type stubs omit it.
    settings = Settings(_env_file=BASE_DIR / ".env")  # type: ignore[call-arg]
    settings.SECRET_KEY = resolve_secret_key(settings)
    return settings


def _env_assignment(key: str, value: str) -> str:
    """Format one .env line. The value is never included in errors."""
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("invalid environment value")
    if value == "" or any(ch in value for ch in (" ", "#", '"', "'", "\\", "\t")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def update_env_many(updates: dict[str, str]) -> None:
    """Write config keys to .env and the current process environment.

    This is the same store used by the model and embedding save endpoints.
    Values are not logged. The next get_settings() call sees the new values.
    """
    if not updates:
        return
    for key, value in updates.items():
        if not key or any(ch in key for ch in ("=", "\n", "\r", "\x00", " ", "#")):
            raise ValueError("invalid environment key")
        if any(ch in value for ch in ("\n", "\r", "\x00")):
            raise ValueError("invalid environment value")

    env_path = BASE_DIR / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        matched: str | None = None
        for key in updates:
            if line.startswith(f"{key}="):
                matched = key
                break
        if matched is None:
            new_lines.append(line)
            continue
        new_lines.append(_env_assignment(matched, updates[matched]))
        remaining.pop(matched, None)
    for key, value in remaining.items():
        new_lines.append(_env_assignment(key, value))

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value
    # Environment variables outrank .env. Clearing the cache is what makes
    # the next get_settings() call return the values just saved.
    get_settings.cache_clear()


def update_env(key: str, value: str):
    """更新 .env 文件中的配置项"""
    update_env_many({key: value})
