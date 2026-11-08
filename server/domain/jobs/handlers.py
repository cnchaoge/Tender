"""各作业类型的执行步骤。运行器在工作线程里调用 dispatch。"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from server.domain.jobs.store import JobCancelled, JobFailed, append_event

logger = logging.getLogger(__name__)


def dispatch(job: dict) -> dict:
    handler = HANDLERS.get(job["type"])
    if handler is None:
        raise JobFailed(f"未知作业类型 {job['type']}")
    try:
        result = handler(job)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise JobFailed(detail) from exc
    return result or {}


def handle_ingest(job: dict) -> dict:
    from server.workers.document_worker import process_document

    payload = job.get("payload") or {}
    doc_id = int(job.get("document_id") or payload.get("document_id") or 0)
    file_path = payload.get("file_path") or ""
    if not doc_id or not file_path:
        raise JobFailed("入库作业缺少文档")

    def on_progress(progress: int, message: str) -> None:
        append_event(job["id"], "progress", {
            "stage": "ingest",
            "progress": progress,
            "message": message,
            "job_id": job["id"],
            "document_id": doc_id,
        })

    try:
        outcome = process_document(doc_id, file_path, on_progress=on_progress)
    except JobCancelled:
        raise
    if outcome == "cancelled":
        raise JobCancelled()
    if outcome != "ready":
        raise JobFailed("文档入库失败", {"document_id": doc_id, "status": outcome})
    return {"document_id": doc_id, "status": "ready"}


def handle_reindex(job: dict) -> dict:
    from server.domain.documents.index_build import execute_rebuild
    from server.domain.jobs.runtime import raise_if_cancelled

    payload = job.get("payload") or {}
    build_id = int(payload.get("build_id") or 0)
    if not build_id:
        raise JobFailed("重建作业缺少 build_id")
    append_event(job["id"], "progress", {
        "stage": "reindex",
        "progress": 10,
        "message": "正在重建索引",
        "job_id": job["id"],
    })
    raise_if_cancelled()
    execute_rebuild(build_id)
    from server.db.sqlite import get_db

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, error FROM index_builds WHERE id = ?", (build_id,))
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise JobFailed("重建记录不存在")
    if row["status"] != "active":
        raise JobFailed(row["error"] or "索引重建失败", {"build_id": build_id})
    return {"build_id": build_id, "status": "active"}


def handle_parse(job: dict) -> dict:
    from server.domain.generation.parse import parse_bid_file
    from server.models import BidParseReq

    req = BidParseReq(**(job.get("payload") or {}))
    resp = parse_bid_file(req, job_id=job["id"])
    data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    append_event(job["id"], "done", {
        "stage": "done",
        "progress": 100,
        "message": "解析完成",
        "job_id": job["id"],
    })
    return data


def handle_plan(job: dict) -> dict:
    from server.domain.generation.outline import plan_bid
    from server.domain.projects.service import save_outline
    from server.models import BidPlanReq

    payload = dict(job.get("payload") or {})
    req = BidPlanReq(**payload)
    resp = plan_bid(req)
    data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    project_id = payload.get("project_id") or job.get("project_id")
    if project_id:
        save_outline(int(project_id), data.get("chapters") or [])
    append_event(job["id"], "done", {
        "stage": "done",
        "progress": 100,
        "message": "目录已写好",
        "job_id": job["id"],
        "chapters": data.get("chapters") or [],
    })
    return data


def handle_generate(job: dict) -> dict:
    from server.domain.generation.run import execute_generate_job
    from server.models import BidGenerateReq

    req = BidGenerateReq(**(job.get("payload") or {}))
    return execute_generate_job(req, job["id"])


def handle_export(job: dict) -> dict:
    from server.domain.export.docx import write_version_docx
    from server.domain.generation.versions import get_bid_version, update_draft_version
    from server.domain.jobs.runtime import raise_if_cancelled

    payload = job.get("payload") or {}
    version_id = int(payload.get("version_id") or 0)
    if not version_id:
        raise JobFailed("导出作业缺少 version_id")
    version = get_bid_version(version_id)
    raise_if_cancelled()
    title = (version.get("parse_result") or {}).get("project_name") or version.get("project_name") or "投标标书"
    path = write_version_docx(version.get("bid_content") or "", title, version_id)
    update_draft_version(version_id, file_path=str(path))
    append_event(job["id"], "done", {
        "stage": "done",
        "progress": 100,
        "message": "Word 已导出",
        "job_id": job["id"],
        "version_id": version_id,
        "file_path": str(path),
        "filename": path.name,
    })
    return {"version_id": version_id, "file_path": str(path), "filename": path.name}


HANDLERS = {
    "document.ingest": handle_ingest,
    "document.reindex": handle_reindex,
    "project.parse": handle_parse,
    "project.plan": handle_plan,
    "bid.generate": handle_generate,
    "bid.export": handle_export,
}
