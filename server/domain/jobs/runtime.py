"""创建作业时抄下的模型快照。执行线程只读这份快照，不跟随后来的设置。"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from server.config import get_settings
from server.domain.documents.index_build import EmbeddingIdentity

_CLOUD_LLM = {"deepseek", "dashscope", "openai", "minimax"}
_CLOUD_EMBED = {"dashscope"}

_pinned: ContextVar[dict | None] = ContextVar("tender_job_runtime", default=None)


def capture_runtime() -> dict:
    """把当前供应商、模型、Embedding 身份和出境标记抄进 runtime_json。"""
    settings = get_settings()
    llm = (settings.LLM_PROVIDER or "ollama").strip().lower()
    embed = (settings.EMBED_PROVIDER or "ollama").strip().lower()
    return {
        "llm_provider": llm,
        "llm_model": _llm_model(settings, llm),
        "embed_provider": embed,
        "embed_model": _embed_model(settings, embed),
        "egress": _egress(llm, embed),
    }


def _llm_model(settings, provider: str) -> str:
    if provider == "deepseek":
        return settings.DEEPSEEK_MODEL
    if provider == "dashscope":
        return settings.DASHSCOPE_MODEL
    if provider == "openai":
        return settings.OPENAI_MODEL
    if provider == "minimax":
        return settings.MINIMAX_MODEL
    if provider == "ollama":
        return settings.OLLAMA_MODEL
    if provider == "mock":
        return "mock"
    return provider


def _embed_model(settings, provider: str) -> str:
    if provider == "ollama":
        return (settings.OLLAMA_EMBED_MODEL or settings.OLLAMA_MODEL or provider).strip()
    if provider == "dashscope":
        return (settings.DASHSCOPE_EMBED_MODEL or provider).strip()
    if provider == "bge":
        return (settings.BGE_MODEL_PATH or "bge").strip()
    if provider == "m3e":
        return (settings.M3E_MODEL_PATH or "m3e").strip()
    if provider == "mock":
        return "mock"
    return provider


def _egress(llm: str, embed: str) -> str:
    if llm in _CLOUD_LLM or embed in _CLOUD_EMBED:
        return "cloud"
    return "local"


def pin_runtime(runtime: dict | None, job_id: int | None = None) -> Token:
    payload = dict(runtime or {})
    payload["_job_id"] = job_id
    return _pinned.set(payload)


def reset_runtime(token: Token) -> None:
    _pinned.reset(token)


def pinned_runtime() -> dict | None:
    return _pinned.get()


def pinned_job_id() -> int | None:
    runtime = _pinned.get()
    if not runtime:
        return None
    job_id = runtime.get("_job_id")
    return int(job_id) if job_id else None


def pinned_generator():
    runtime = _pinned.get()
    if not runtime or "_generator" not in runtime:
        return None
    return runtime.get("_generator")


def pinned_embedder():
    runtime = _pinned.get()
    if not runtime or "_embedder" not in runtime:
        return None
    return runtime.get("_embedder")


def pinned_embed_identity() -> EmbeddingIdentity | None:
    runtime = _pinned.get()
    if not runtime or not runtime.get("embed_provider"):
        return None
    return EmbeddingIdentity(
        provider=str(runtime["embed_provider"]),
        model=str(runtime.get("embed_model") or runtime["embed_provider"]),
    )


def attach_clients(runtime: dict) -> dict:
    """按快照构造生成器和嵌入器，挂在这份运行时上。密钥仍从当前环境读取。"""
    bound = dict(runtime or {})
    bound["_generator"] = build_generator(bound)
    bound["_embedder"] = build_embedder(bound)
    return bound


def build_generator(runtime: dict):
    from server.core.generator.llm import (
        DashScopeGenerator,
        DeepSeekGenerator,
        MiniMaxGenerator,
        MockGenerator,
        OllamaGenerator,
        OpenAIGenerator,
    )

    provider = (runtime.get("llm_provider") or "ollama").strip().lower()
    model = runtime.get("llm_model") or None
    if provider == "mock":
        return MockGenerator()
    if provider == "deepseek":
        return DeepSeekGenerator(model=model)
    if provider == "dashscope":
        return DashScopeGenerator(model=model)
    if provider == "openai":
        return OpenAIGenerator(model=model)
    if provider == "minimax":
        return MiniMaxGenerator(model=model)
    if provider == "ollama":
        return OllamaGenerator(model=model)
    raise ValueError(f"未知的 LLM provider: {provider}")


def build_embedder(runtime: dict):
    from server.core.embedder.embedder import (
        BGEEmbedder,
        DashScopeEmbedder,
        M3EEmbedder,
        MockEmbedder,
        OllamaEmbedder,
    )

    provider = (runtime.get("embed_provider") or "ollama").strip().lower()
    model = runtime.get("embed_model") or None
    if provider == "mock":
        return MockEmbedder()
    if provider == "ollama":
        return OllamaEmbedder(model=model)
    if provider == "dashscope":
        return DashScopeEmbedder(model=model)
    if provider == "bge":
        return BGEEmbedder()
    if provider == "m3e":
        return M3EEmbedder()
    raise ValueError(f"未知的 Embedding provider: {provider}")


def raise_if_cancelled() -> None:
    """运行中的作业在安全点查看 cancel_requested。没有钉住的作业则什么都不做。"""
    job_id = pinned_job_id()
    if not job_id:
        return
    from server.domain.jobs.store import JobCancelled, is_cancel_requested

    if is_cancel_requested(job_id):
        raise JobCancelled()


def runtime_public(runtime: dict | None) -> dict:
    """去掉挂在快照上的客户端对象，只留下可序列化的字段。"""
    data = dict(runtime or {})
    return {
        "llm_provider": data.get("llm_provider"),
        "llm_model": data.get("llm_model"),
        "embed_provider": data.get("embed_provider"),
        "embed_model": data.get("embed_model"),
        "egress": data.get("egress"),
    }


def as_jsonable(runtime: dict | None) -> dict[str, Any]:
    return runtime_public(runtime)
