"""进程内作业运行器。

和 API 同一个解释器，不开第二个进程去碰 SQLite / Chroma。
`bid.generate` 同时最多 1 笔，入库和重建共享最多 2 笔。本地模型和云端模型同一限制。
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from server.domain.jobs.store import (
    JobCancelled,
    JobFailed,
    finish,
    list_queued,
    mark_running,
    request_cancel,
)

logger = logging.getLogger(__name__)

_LIMITS = {
    "ingest": 2,
    "generate": 1,
    "other": 2,
}
_POOL_SIZE = sum(_LIMITS.values())

_lock = threading.Lock()
_inflight = {"ingest": 0, "generate": 0, "other": 0}
_stop = threading.Event()
_wake = threading.Event()
_thread: Optional[threading.Thread] = None
_pool: Optional[ThreadPoolExecutor] = None


def _bucket(job_type: str) -> str:
    if job_type in {"document.ingest", "document.reindex"}:
        return "ingest"
    if job_type == "bid.generate":
        return "generate"
    return "other"


def ensure_runner() -> None:
    global _thread, _pool
    with _lock:
        if _thread is not None and _thread.is_alive():
            _wake.set()
            return
        _stop.clear()
        _pool = ThreadPoolExecutor(max_workers=_POOL_SIZE, thread_name_prefix="tender-job")
        _thread = threading.Thread(target=_loop, name="tender-job-dispatch", daemon=True)
        _thread.start()
    _wake.set()


def shutdown_runner(wait: bool = False) -> None:
    global _thread, _pool
    _stop.set()
    _wake.set()
    with _lock:
        pool = _pool
        thread = _thread
        _pool = None
        _thread = None
        for key in _inflight:
            _inflight[key] = 0
    if pool is not None:
        pool.shutdown(wait=wait, cancel_futures=True)
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.0 if not wait else 5.0)


def _loop() -> None:
    while not _stop.is_set():
        claimed = _claim()
        if claimed is None:
            _wake.wait(0.4)
            _wake.clear()
            continue
        job, bucket = claimed
        pool = _pool
        if pool is None:
            _release(bucket)
            return
        try:
            pool.submit(_execute, job, bucket)
        except RuntimeError:
            _release(bucket)
            logger.exception("job pool rejected job_id=%s", job["id"])
            return


def _claim():
    try:
        rows = list_queued()
    except Exception:
        logger.exception("list queued jobs failed")
        return None
    for row in rows:
        if row.get("cancel_requested"):
            try:
                request_cancel(row["id"])
            except Exception:
                logger.exception("cancel queued job %s failed", row["id"])
            continue
        bucket = _bucket(row["type"])
        with _lock:
            if _inflight[bucket] >= _LIMITS[bucket]:
                continue
            if not mark_running(row["id"]):
                continue
            _inflight[bucket] += 1
            return row, bucket
    return None


def _release(bucket: str) -> None:
    with _lock:
        _inflight[bucket] = max(0, _inflight[bucket] - 1)
    _wake.set()


def _execute(job: dict, bucket: str) -> None:
    from server.domain.jobs.handlers import dispatch
    from server.domain.jobs.runtime import attach_clients, pin_runtime, reset_runtime

    token = pin_runtime(attach_clients(job.get("runtime") or {}), job_id=job["id"])
    try:
        if job.get("cancel_requested"):
            request_cancel(job["id"])
            return
        result = dispatch(job)
        # 执行期间如果已经置了取消，并且处理器没有自己收成 cancelled，这里补上。
        from server.domain.jobs.store import get_job_row, is_cancel_requested

        current = get_job_row(job["id"])
        if current["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return
        if is_cancel_requested(job["id"]):
            finish(job["id"], "cancelled", message="已取消", result=result)
            return
        finish(job["id"], "succeeded", message="完成", result=result)
    except JobCancelled:
        try:
            finish(job["id"], "cancelled", message="已取消")
        except Exception:
            logger.exception("mark cancelled failed job_id=%s", job["id"])
    except JobFailed as exc:
        logger.info("job %s failed: %s", job["id"], exc)
        try:
            finish(job["id"], "failed", message=str(exc) or "失败", result=exc.result or {"error": str(exc)})
        except Exception:
            logger.exception("mark failed failed job_id=%s", job["id"])
    except Exception as exc:
        logger.exception("job %s crashed", job["id"])
        try:
            finish(job["id"], "failed", message=str(exc) or "失败", result={"error": str(exc)})
        except Exception:
            logger.exception("mark crashed failed job_id=%s", job["id"])
    finally:
        reset_runtime(token)
        _release(bucket)


def inflight_counts() -> dict:
    with _lock:
        return dict(_inflight)
