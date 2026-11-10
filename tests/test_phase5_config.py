"""阶段 5：作业执行读快照；换模型不必重启；云端说明写进 runtime。"""
import threading
import time
from pathlib import Path

from server.config import get_settings
from server.db import sqlite as sqlite_mod
from server.domain.documents import files as files_mod
from server.domain.jobs import handlers as handlers_mod
from server.domain.jobs.runtime import CLOUD_EGRESS_NOTE
from server.domain.jobs.service import enqueue
from server.domain.jobs.store import get_job_row
from server.workers.runner import shutdown_runner


def _use_temp_db(monkeypatch, tmp_path: Path) -> None:
    shutdown_runner(wait=True)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sqlite_mod, "DB_PATH", data / "tender.db")
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", data)
    monkeypatch.setattr(files_mod, "DATA_DIR", data)
    sqlite_mod.init_db()


def _wait_status(job_id: int, wanted: set[str], timeout: float = 4.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = get_job_row(job_id)
        if last["status"] in wanted:
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_modules_do_not_bind_settings_at_import():
    root = Path("server")
    for rel in (
        "core/generator/llm.py",
        "core/embedder/embedder.py",
        "db/chromadb.py",
        "api/bid.py",
    ):
        for line in (root / rel).read_text(encoding="utf-8").splitlines():
            if line.startswith("settings = get_settings()"):
                raise AssertionError(rel)


def test_next_job_uses_new_model_and_running_job_keeps_snapshot(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()
    seen = []

    def run(job):
        from server.core.generator.llm import get_generator

        seen.append(get_generator().model)
        if len(seen) == 1:
            started.set()
            release.wait(3)
        return {"ok": True}

    monkeypatch.setitem(handlers_mod.HANDLERS, "project.plan", run)
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "local-old")
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "embed-old")
    get_settings.cache_clear()
    try:
        first = enqueue("project.plan", payload={"keep": "old"})
        assert first["runtime"]["llm_provider"] == "ollama"
        assert first["runtime"]["llm_model"] == "local-old"
        assert first["runtime"]["embed_model"] == "embed-old"
        assert first["runtime"]["egress"] == "local"
        assert "note" not in first["runtime"]
        assert started.wait(3)
        assert seen == ["local-old"]

        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("EMBED_PROVIDER", "dashscope")
        monkeypatch.setenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v3")
        get_settings.cache_clear()

        # 设置已经变了，正在跑的这笔仍用创建时抄下的模型。
        assert get_job_row(first["id"])["runtime"]["llm_model"] == "local-old"
        assert seen == ["local-old"]
        release.set()
        assert _wait_status(first["id"], {"succeeded"})["status"] == "succeeded"
        assert seen == ["local-old"]

        second = enqueue("project.plan", payload={"keep": "new"})
        finished = _wait_status(second["id"], {"succeeded"})
        assert finished["runtime"]["llm_provider"] == "deepseek"
        assert finished["runtime"]["llm_model"] == "deepseek-chat"
        assert finished["runtime"]["embed_provider"] == "dashscope"
        assert finished["runtime"]["egress"] == "cloud"
        assert finished["runtime"]["note"] == CLOUD_EGRESS_NOTE
        assert "离开本机" in finished["runtime"]["note"]
        assert seen == ["local-old", "deepseek-chat"]
    finally:
        release.set()
        shutdown_runner(wait=True)
        get_settings.cache_clear()
