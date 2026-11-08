"""作业查询、取消和事件流。创建由各业务入口入队，这里也接受直接创建。"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.deps import get_current_user
from server.domain.jobs.service import cancel_job, enqueue, get_job, list_events, list_jobs
from server.domain.jobs.store import TERMINAL

router = APIRouter(prefix="/api/jobs", tags=["作业"], dependencies=[Depends(get_current_user)])

_CREATE_TYPES = {
    "document.ingest",
    "document.reindex",
    "project.parse",
    "project.plan",
    "bid.generate",
    "bid.export",
}


class JobCreateReq(BaseModel):
    type: str
    payload: dict = {}
    project_id: Optional[int] = None
    document_id: Optional[int] = None


def _sse(payload: dict) -> bytes:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@router.post("")
def create_job(req: JobCreateReq, user: dict = Depends(get_current_user)):
    if req.type not in _CREATE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的作业类型")
    payload = dict(req.payload or {})
    project_id = req.project_id if req.project_id is not None else payload.get("project_id")
    document_id = req.document_id if req.document_id is not None else payload.get("document_id")
    idempotency_key = None
    if req.type == "bid.generate":
        from server.domain.jobs.service import generate_idempotency_key

        idempotency_key = generate_idempotency_key(
            project_id,
            payload.get("parse_result") or {},
            payload.get("materials") or [],
            payload.get("strategy") or "",
        )
    return enqueue(
        req.type,
        payload=payload,
        project_id=project_id,
        document_id=document_id,
        created_by=user.get("id"),
        idempotency_key=idempotency_key,
    )


@router.get("")
def get_jobs(
    type: Optional[str] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    statuses = [item.strip() for item in status.split(",")] if status else None
    return list_jobs(job_type=type, project_id=project_id, statuses=statuses, limit=limit)


@router.get("/{job_id}")
def read_job(job_id: int):
    return get_job(job_id)


@router.post("/{job_id}/cancel")
def cancel(job_id: int):
    return cancel_job(job_id)


@router.get("/{job_id}/log")
def read_log(job_id: int, after: int = 0):
    get_job(job_id)
    return {"events": list_events(job_id, after)}


@router.get("/{job_id}/events")
async def stream_events(
    job_id: int,
    after: int = 0,
    cancel_on_disconnect: bool = False,
):
    """重连时从 after 之后续传，缺省从 0 开始，所以会先把已经写下的事件再推一遍。

    只有生成页这条订阅传 cancel_on_disconnect。入库和重建关掉页面后继续跑。
    """
    job = get_job(job_id)
    # 生成以外的作业忽略这个参数，避免工作台旁观把入库停掉。
    disconnect_cancels = bool(cancel_on_disconnect) and job["type"] == "bid.generate"

    async def gen():
        cursor = after
        completed = False
        try:
            while True:
                current = get_job(job_id)
                events = list_events(job_id, cursor)
                for event in events:
                    cursor = event["seq"]
                    yield _sse(event["payload"])
                    if event["payload"].get("stage") in {"done", "violation_fail", "cancelled", "error"}:
                        completed = True
                        return
                if current["status"] in TERMINAL and not events:
                    completed = True
                    return
                await asyncio.sleep(0.05)
        finally:
            if disconnect_cancels and not completed:
                try:
                    cancel_job(job_id)
                except Exception:
                    pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
