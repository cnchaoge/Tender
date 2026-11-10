"""阶段 4：统一作业、取消、重启对账和并发上限。"""
import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from server.db import sqlite as sqlite_mod
from server.domain.documents import files as files_mod
from server.domain.jobs import runtime as runtime_mod
from server.domain.jobs import handlers as handlers_mod
from server.domain.jobs.service import enqueue, enqueue_generate
from server.domain.jobs.store import (
    get_job_row,
    is_cancel_requested,
    list_events,
    reconcile_after_restart,
)
from server.domain.jobs.store import JobCancelled
from server.models import BidGenerateReq
from server.workers.runner import ensure_runner, inflight_counts, shutdown_runner

PARSE = {
    "project_name": "作业测试工程",
    "deadline": "10天",
    "requirements": ["执照"],
    "qualification": ["ISO"],
    "scoring": {},
}
CHAPTERS = [
    {"index": 0, "name": "第一章 投标函", "description": "函"},
    {"index": 1, "name": "第二章 技术方案", "description": "方案"},
]


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    shutdown_runner(wait=True)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sqlite_mod, "DB_PATH", data / "tender.db")
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", data)
    monkeypatch.setattr(files_mod, "DATA_DIR", data)
    sqlite_mod.init_db()
    return data


def _wait_status(job_id: int, wanted: set[str], timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = get_job_row(job_id)
        if last["status"] in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(last)


@pytest.fixture(autouse=True)
def _stop_runner():
    shutdown_runner(wait=True)
    yield
    shutdown_runner(wait=True)


def test_existing_database_gains_job_tables(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    db_path = data / "tender.db"
    monkeypatch.setattr(sqlite_mod, "DB_PATH", db_path)
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", data)
    monkeypatch.setattr(files_mod, "DATA_DIR", data)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (3);
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE bid_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            parse_result_json TEXT,
            bid_content TEXT,
            strategy TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            material_ids TEXT,
            project_id INTEGER
        );
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            purchaser TEXT NOT NULL DEFAULT '',
            deadline TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            parse_id INTEGER,
            name_edited INTEGER NOT NULL DEFAULT 0,
            deadline_edited INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO documents (filename, file_type, file_path, file_size, status)
        VALUES ('keep.txt', 'txt', 'library/1/original.txt', 4, 'ready');
        INSERT INTO bid_versions (project_name, bid_content, material_ids, project_id)
        VALUES ('旧项目', '旧正文', '[]', 1);
        INSERT INTO projects (name) VALUES ('旧项目');
        """
    )
    conn.commit()
    conn.close()

    sqlite_mod.init_db()
    conn = sqlite_mod.get_db()
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "jobs" in tables
        assert "job_events" in tables
        version_cols = {row[1] for row in conn.execute("PRAGMA table_info(bid_versions)")}
        assert {"status", "job_id", "parse_id", "outline_json", "runtime_json"} <= version_cols
        project_cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
        assert "outline_json" in project_cols
        assert conn.execute("SELECT bid_content FROM bid_versions").fetchone()[0] == "旧正文"
        assert conn.execute("SELECT status FROM documents").fetchone()[0] == "ready"
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    finally:
        conn.close()


def test_concurrency_limits_one_generate_and_two_ingests(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    release = threading.Event()
    entered = []
    entered_lock = threading.Lock()

    def block(kind):
        def _run(job):
            with entered_lock:
                entered.append((kind, job["id"]))
            release.wait(3)
            return {"ok": True, "kind": kind}
        return _run

    monkeypatch.setitem(handlers_mod.HANDLERS, "bid.generate", block("generate"))
    monkeypatch.setitem(handlers_mod.HANDLERS, "document.ingest", block("ingest"))

    generates = []
    for index in range(2):
        payload = {
            "parse_result": {**PARSE, "project_name": f"工程{index}"},
            "materials": [index + 1],
            "strategy": "综合均衡型",
            "project_id": None,
            "chapters": [],
        }
        generates.append(enqueue(
            "bid.generate",
            payload=payload,
            idempotency_key=f"gen-{index}",
        ))
    ingests = [
        enqueue("document.ingest", payload={"file_path": f"/tmp/{i}.txt", "document_id": i + 1}, document_id=i + 1)
        for i in range(3)
    ]
    ensure_runner()

    deadline = time.time() + 3
    while time.time() < deadline:
        states = [get_job_row(job["id"])["status"] for job in generates + ingests]
        running_gen = sum(
            1 for job in generates if get_job_row(job["id"])["status"] == "running"
        )
        running_ing = sum(
            1 for job in ingests if get_job_row(job["id"])["status"] == "running"
        )
        queued_gen = sum(
            1 for job in generates if get_job_row(job["id"])["status"] == "queued"
        )
        queued_ing = sum(
            1 for job in ingests if get_job_row(job["id"])["status"] == "queued"
        )
        if running_gen == 1 and queued_gen == 1 and running_ing == 2 and queued_ing == 1:
            break
        time.sleep(0.02)
    else:
        raise AssertionError({
            "states": states,
            "inflight": inflight_counts(),
            "entered": entered,
        })

    counts = inflight_counts()
    assert counts["generate"] == 1
    assert counts["ingest"] == 2
    release.set()
    for job in generates + ingests:
        assert _wait_status(job["id"], {"succeeded"})["status"] == "succeeded"


def test_same_generate_key_reuses_unfinished_job(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    release = threading.Event()

    def block(job):
        release.wait(3)
        return {"ok": True}

    monkeypatch.setitem(handlers_mod.HANDLERS, "bid.generate", block)
    req = BidGenerateReq(parse_result=dict(PARSE), materials=[3, 1], strategy="技术优先型", project_id=None)
    first = enqueue_generate(req)
    second = enqueue_generate(req)
    assert second["id"] == first["id"]
    assert second["status"] in {"queued", "running"}

    other = BidGenerateReq(parse_result=dict(PARSE), materials=[3, 1], strategy="成本控制型")
    third = enqueue_generate(other)
    assert third["id"] != first["id"]

    release.set()
    _wait_status(first["id"], {"succeeded"})
    _wait_status(third["id"], {"succeeded"})
    again = enqueue_generate(req)
    assert again["id"] != first["id"]


def test_cancelled_generate_does_not_block_a_new_one(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.setitem(handlers_mod.HANDLERS, "bid.generate", lambda job: {"ok": True})
    req = BidGenerateReq(parse_result=dict(PARSE), materials=[1], strategy="综合均衡型")
    first = enqueue_generate(req)
    from server.domain.jobs.service import cancel_job

    cancelled = cancel_job(first["id"])
    assert cancelled["status"] == "cancelled"
    second = enqueue_generate(req)
    assert second["id"] != first["id"]
    assert _wait_status(second["id"], {"succeeded"})["status"] == "succeeded"


def test_cancel_keeps_written_chapters_and_skips_later_model_calls(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    from server.domain.generation import draft
    from server.domain.generation import run as generation_run

    calls = {"review": 0, "stream": 0}

    class Gen:
        def generate(self, prompt, system="", **kwargs):
            calls["review"] += 1
            return '{"passed": true, "score": 90, "issues": [], "suggestions": []}'

        def generate_stream(self, prompt, system="", **kwargs):
            calls["stream"] += 1
            yield "# 投标函\n第一段已经写好。\n"
            yield "# 技术方案\n这段不该留下。\n"

    monkeypatch.setattr(generation_run, "get_generator", lambda: Gen())
    monkeypatch.setattr(generation_run, "_retrieve_materials_text", lambda *args, **kwargs: "素材")
    monkeypatch.setattr(generation_run, "get_violation_checker", lambda: type("V", (), {
        "check_bid_content": lambda self, content, parse: {"passed": True, "violations": [], "summary": {}},
    })())
    monkeypatch.setattr(draft, "review_bid", lambda content, parse: {"passed": True, "score": 90, "issues": [], "suggestions": []})

    req = BidGenerateReq(
        parse_result=dict(PARSE),
        materials=[1],
        chapters=list(CHAPTERS),
        strategy="综合均衡型",
    )
    from server.domain.jobs.runtime import capture_runtime, runtime_public
    from server.domain.jobs.store import insert_job

    job = insert_job(
        job_type="bid.generate",
        payload=req.model_dump(),
        runtime=runtime_public(capture_runtime()),
        idempotency_key="cancel-me",
    )
    # 还在跑正文时置取消。作业仍是 queued，不能走「排队直接取消」。
    conn = sqlite_mod.get_db()
    try:
        conn.execute("UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job["id"],))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(JobCancelled):
        generation_run.execute_generate_job(req, job["id"])

    conn = sqlite_mod.get_db()
    try:
        row = conn.execute(
            "SELECT status, bid_content FROM bid_versions WHERE job_id = ?",
            (job["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "cancelled"
    assert "第一段已经写好" in row["bid_content"]
    assert "这段不该留下" not in row["bid_content"]
    kinds = [event["payload"].get("stage") for event in list_events(job["id"])]
    assert "chapter_done" in kinds
    assert "cancelled" in kinds
    assert "reviewing" not in kinds
    assert calls["review"] == 0
    assert calls["stream"] == 1


def test_restart_interrupts_generate_and_requeues_ingest(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    from server.workers import document_worker as worker_mod

    monkeypatch.setattr(worker_mod, "delete_doc_chunks", lambda doc_id: None)
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count)
               VALUES ('half.txt', 'txt', 'library/1/original.txt', 4, 'processing', 1)"""
        )
        doc_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text, metadata) VALUES (?, 0, '半成品', '{}')",
            (doc_id,),
        )
        cur.execute(
            """INSERT INTO jobs
               (type, status, progress, message, payload_json, runtime_json, document_id)
               VALUES ('document.ingest', 'running', 40, '嵌入中', ?, '{}', ?)""",
            (json.dumps({"file_path": "library/1/original.txt", "document_id": doc_id}), doc_id),
        )
        ingest_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO bid_versions
               (project_name, bid_content, strategy, status, job_id)
               VALUES ('半成品项目', '已经写好的章', '综合均衡型', 'draft', 0)"""
        )
        version_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO jobs
               (type, status, progress, message, payload_json, runtime_json, project_id)
               VALUES ('bid.generate', 'running', 30, '生成中', '{}', '{}', NULL)"""
        )
        generate_id = int(cur.lastrowid)
        cur.execute("UPDATE bid_versions SET job_id = ? WHERE id = ?", (generate_id, version_id))
        conn.commit()
    finally:
        conn.close()

    ran = []
    monkeypatch.setitem(handlers_mod.HANDLERS, "bid.generate", lambda job: ran.append(("generate", job["id"])) or {"ok": True})
    monkeypatch.setitem(handlers_mod.HANDLERS, "document.ingest", lambda job: ran.append(("ingest", job["id"])) or {"ok": True})

    summary = reconcile_after_restart()
    assert summary["generate_interrupted"] == 1
    assert summary["ingest_requeued"] == 1
    assert get_job_row(generate_id)["status"] == "interrupted"
    assert get_job_row(ingest_id)["status"] == "queued"

    conn = sqlite_mod.get_db()
    try:
        version = conn.execute("SELECT status, bid_content FROM bid_versions WHERE id = ?", (version_id,)).fetchone()
        chunks = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()[0]
        doc = conn.execute("SELECT status, chunk_count FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    assert version["status"] == "interrupted"
    assert version["bid_content"] == "已经写好的章"
    assert chunks == 0
    assert doc["status"] == "pending"
    assert doc["chunk_count"] == 0

    ensure_runner()
    assert _wait_status(ingest_id, {"succeeded"})["status"] == "succeeded"
    time.sleep(0.2)
    assert get_job_row(generate_id)["status"] == "interrupted"
    assert [item[0] for item in ran] == ["ingest"]
    assert is_cancel_requested(generate_id) is False


def test_runtime_snapshot_survives_a_later_settings_change(monkeypatch):
    from server.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "snapshot-model")
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "embed-snapshot")
    get_settings.cache_clear()
    try:
        captured = runtime_mod.capture_runtime()
        token = runtime_mod.pin_runtime(runtime_mod.attach_clients(captured), job_id=1)
        try:
            monkeypatch.setenv("LLM_PROVIDER", "mock")
            monkeypatch.setenv("OLLAMA_MODEL", "other-model")
            get_settings.cache_clear()
            from server.core.generator.llm import get_generator

            generator = get_generator()
            assert getattr(generator, "model", None) == "snapshot-model"
            assert captured["llm_model"] == "snapshot-model"
            assert captured["egress"] == "local"
            fresh = runtime_mod.capture_runtime()
            assert fresh["llm_provider"] == "mock"
            assert fresh["llm_model"] == "mock"
        finally:
            runtime_mod.reset_runtime(token)
    finally:
        get_settings.cache_clear()


def test_document_status_is_projection_of_latest_ingest(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count)
               VALUES ('a.txt', 'txt', 'library/9/original.txt', 3, 'pending', 0)"""
        )
        doc_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    seen = {}

    def succeed(job):
        seen["runtime"] = dict(job["runtime"])
        from server.domain.jobs.store import project_document_status
        project_document_status(doc_id, "running")
        return {"document_id": doc_id, "status": "ready"}

    monkeypatch.setitem(handlers_mod.HANDLERS, "document.ingest", succeed)
    job = enqueue(
        "document.ingest",
        payload={"file_path": "library/9/original.txt", "document_id": doc_id},
        document_id=doc_id,
    )
    assert get_job_row(job["id"])["runtime"]["llm_provider"]
    finished = _wait_status(job["id"], {"succeeded"})
    assert finished["result"]["document_id"] == doc_id
    conn = sqlite_mod.get_db()
    try:
        status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
    finally:
        conn.close()
    assert status == "ready"
    assert seen["runtime"]["egress"] in {"local", "cloud"}
    assert "llm_model" in seen["runtime"]


def test_generate_stream_disconnect_cancels_the_job(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    from server.api import bid as bid_api

    def linger(job):
        for _ in range(40):
            if is_cancel_requested(job["id"]):
                raise JobCancelled()
            time.sleep(0.05)
        return {"ok": True}

    monkeypatch.setitem(handlers_mod.HANDLERS, "bid.generate", linger)
    req = BidGenerateReq(parse_result=dict(PARSE), materials=[1], strategy="综合均衡型")

    async def _close_early():
        response = await bid_api.generate_bid_stream(req)
        iterator = response.body_iterator
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0.15)
        pending.cancel()
        try:
            await pending
        except (asyncio.CancelledError, StopAsyncIteration, Exception):
            pass

    asyncio.run(_close_early())
    conn = sqlite_mod.get_db()
    try:
        job_id = int(conn.execute(
            "SELECT id FROM jobs WHERE type = 'bid.generate' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0])
    finally:
        conn.close()
    finished = _wait_status(job_id, {"cancelled", "failed", "succeeded"})
    assert finished["status"] == "cancelled"
