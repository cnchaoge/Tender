"""作业门面。路由和旧的 schedule_* 都从这里入队。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from server.domain.jobs.runtime import capture_runtime, runtime_public
from server.domain.jobs.store import (
    find_active_ingest,
    find_active_reindex,
    get_job_row,
    insert_job,
    list_events,
    list_job_rows,
    public_job,
    request_cancel,
)

__all__ = [
    "cancel_job",
    "enqueue",
    "enqueue_generate",
    "generate_idempotency_key",
    "get_job",
    "list_events",
    "list_jobs",
    "public_job",
]


def enqueue(
    job_type: str,
    *,
    payload: dict | None = None,
    project_id: int | None = None,
    document_id: int | None = None,
    created_by: int | None = None,
    idempotency_key: str | None = None,
    message: str = "排队中",
) -> dict:
    from server.workers.runner import ensure_runner

    if job_type == "document.ingest" and document_id is not None:
        existing = find_active_ingest(int(document_id))
        if existing is not None:
            ensure_runner()
            return existing
    if job_type == "document.reindex":
        build_id = int((payload or {}).get("build_id") or 0)
        if build_id:
            existing = find_active_reindex(build_id)
            if existing is not None:
                ensure_runner()
                return existing
    runtime = runtime_public(capture_runtime())
    job = insert_job(
        job_type=job_type,
        payload=payload or {},
        runtime=runtime,
        idempotency_key=idempotency_key,
        project_id=project_id,
        document_id=document_id,
        created_by=created_by,
        message=message,
    )
    ensure_runner()
    return job


def generate_idempotency_key(project_id, parse_result: dict, materials: list, strategy: str) -> str:
    body = {
        "project_id": project_id,
        "strategy": strategy or "",
        "materials": sorted(int(item) for item in (materials or [])),
        "parse_result": parse_result or {},
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enqueue_generate(req, created_by: int | None = None) -> dict:
    payload = req.model_dump() if hasattr(req, "model_dump") else dict(req)
    key = generate_idempotency_key(
        payload.get("project_id"),
        payload.get("parse_result") or {},
        payload.get("materials") or [],
        payload.get("strategy") or "",
    )
    return enqueue(
        "bid.generate",
        payload=payload,
        project_id=payload.get("project_id"),
        idempotency_key=key,
        created_by=created_by,
        message="排队等待生成",
    )


def get_job(job_id: int) -> dict:
    try:
        return get_job_row(int(job_id))
    except KeyError:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="作业不存在") from None


def list_jobs(**kwargs: Any) -> dict:
    return {"jobs": list_job_rows(**kwargs)}


def cancel_job(job_id: int) -> dict:
    try:
        return request_cancel(int(job_id))
    except KeyError:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="作业不存在") from None
