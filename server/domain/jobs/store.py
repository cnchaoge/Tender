"""jobs 与 job_events 的读写。连接在调用时打开，便于测试替换数据库。"""
from __future__ import annotations

import json
from typing import Any

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
UNFINISHED = {"queued", "running"}
GENERATE_TYPE = "bid.generate"
INGEST_TYPES = {"document.ingest", "document.reindex"}

# 文档状态是最近一次入库作业的投影。
_DOC_STATUS = {
    "queued": "pending",
    "running": "processing",
    "succeeded": "ready",
    "failed": "failed",
    "cancelled": "cancelled",
    "interrupted": "pending",
}


class JobCancelled(Exception):
    """合作式取消。已经写入的草稿和事件保留。"""


class JobFailed(Exception):
    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result or {}


def _connect():
    from server.db.sqlite import SQLITE_BUSY_TIMEOUT_MS, get_db

    conn = get_db()
    try:
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    except Exception:
        pass
    return conn


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def public_job(row) -> dict:
    return {
        "id": int(row["id"]),
        "type": row["type"],
        "status": row["status"],
        "progress": int(row["progress"] or 0),
        "message": row["message"] or "",
        "payload": _loads(row["payload_json"], {}),
        "result": _loads(row["result_json"], None) if row["result_json"] else None,
        "cancel_requested": bool(row["cancel_requested"]),
        "runtime": _loads(row["runtime_json"], {}),
        "idempotency_key": row["idempotency_key"],
        "project_id": row["project_id"],
        "document_id": row["document_id"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def public_event(row) -> dict:
    return {
        "id": int(row["id"]),
        "job_id": int(row["job_id"]),
        "seq": int(row["seq"]),
        "kind": row["kind"],
        "payload": _loads(row["payload_json"], {}),
        "created_at": row["created_at"],
    }


def insert_job(
    *,
    job_type: str,
    payload: dict,
    runtime: dict,
    idempotency_key: str | None = None,
    project_id: int | None = None,
    document_id: int | None = None,
    created_by: int | None = None,
    message: str = "排队中",
) -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        if idempotency_key and job_type == GENERATE_TYPE:
            existing = _unfinished_by_key(cur, idempotency_key)
            if existing is not None:
                conn.commit()
                return public_job(existing)
        cur.execute(
            """INSERT INTO jobs
               (type, status, progress, message, payload_json, result_json,
                cancel_requested, runtime_json, idempotency_key, project_id,
                document_id, created_by)
               VALUES (?, 'queued', 0, ?, ?, NULL, 0, ?, ?, ?, ?, ?)""",
            (
                job_type,
                message,
                json.dumps(payload or {}, ensure_ascii=False),
                json.dumps(runtime or {}, ensure_ascii=False),
                idempotency_key,
                project_id,
                document_id,
                created_by,
            ),
        )
        job_id = int(cur.lastrowid)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    job = get_job_row(job_id)
    if job_type == "document.ingest" and document_id:
        project_document_status(int(document_id), "queued")
    return job


def _unfinished_by_key(cur, key: str):
    """同一份生成还在排队或运行时复用那一笔。已经请求取消的不占用这个键。

    运行中的取消要等到安全点才变成 cancelled。在那之前新的一笔必须能排上，
    否则取消了的生成会挡住下一次相同内容的生成。
    """
    cur.execute(
        """SELECT * FROM jobs
           WHERE idempotency_key = ? AND status IN ('queued', 'running')
             AND cancel_requested = 0
           ORDER BY id DESC
           LIMIT 1""",
        (key,),
    )
    return cur.fetchone()


def find_active_ingest(document_id: int) -> dict | None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM jobs
               WHERE type = 'document.ingest' AND document_id = ?
                 AND status IN ('queued', 'running')
               ORDER BY id DESC
               LIMIT 1""",
            (int(document_id),),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return public_job(row) if row is not None else None


def find_active_reindex(build_id: int) -> dict | None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM jobs
               WHERE type = 'document.reindex' AND status IN ('queued', 'running')
               ORDER BY id DESC"""
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        payload = _loads(row["payload_json"], {})
        if int(payload.get("build_id") or 0) == int(build_id):
            return public_job(row)
    return None


def get_job_row(job_id: int) -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id),))
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError(job_id)
    return public_job(row)


def list_job_rows(
    *,
    job_type: str | None = None,
    project_id: int | None = None,
    statuses: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if job_type:
        clauses.append("type = ?")
        params.append(job_type)
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(int(project_id))
    if statuses:
        marks = ",".join("?" for _ in statuses)
        clauses.append(f"status IN ({marks})")
        params.extend(statuses)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(int(limit))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ?",
            params,
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [public_job(row) for row in rows]


def list_queued() -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM jobs
               WHERE status = 'queued'
               ORDER BY id ASC"""
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [public_job(row) for row in rows]


def mark_running(job_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE jobs
               SET status = 'running',
                   started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP,
                   message = CASE WHEN message = '' OR message = '排队中' THEN '进行中' ELSE message END
               WHERE id = ? AND status = 'queued'""",
            (int(job_id),),
        )
        changed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if changed:
        try:
            job = get_job_row(job_id)
        except KeyError:
            return True
        if job["type"] == "document.ingest" and job["document_id"]:
            project_document_status(int(job["document_id"]), "running")
    return bool(changed)


def is_cancel_requested(job_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT cancel_requested, status FROM jobs WHERE id = ?",
            (int(job_id),),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return False
    if row["status"] == "cancelled":
        return True
    return bool(row["cancel_requested"])


def request_cancel(job_id: int) -> dict:
    """排队中的作业直接 cancelled。运行中的只置 cancel_requested，等安全点停下。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id),))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            raise KeyError(job_id)
        status = row["status"]
        if status in TERMINAL:
            conn.commit()
            return public_job(row)
        if status == "queued":
            cur.execute(
                """UPDATE jobs
                   SET status = 'cancelled',
                       cancel_requested = 1,
                       message = '已取消',
                       finished_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'queued'""",
                (int(job_id),),
            )
        else:
            cur.execute(
                """UPDATE jobs
                   SET cancel_requested = 1,
                       message = '正在取消',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (int(job_id),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    job = get_job_row(job_id)
    if job["status"] == "cancelled" and job["type"] == "document.ingest" and job["document_id"]:
        project_document_status(int(job["document_id"]), "cancelled")
    if job["status"] == "cancelled":
        append_event(job_id, "cancelled", {"stage": "cancelled", "message": "已取消", "progress": job["progress"]})
    return job


def finish(job_id: int, status: str, *, message: str = "", result: dict | None = None) -> dict:
    if status not in TERMINAL:
        raise ValueError(status)
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE jobs
               SET status = ?,
                   message = ?,
                   result_json = ?,
                   progress = CASE WHEN ? = 'succeeded' THEN 100 ELSE progress END,
                   finished_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status IN ('queued', 'running')""",
            (
                status,
                message,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                status,
                int(job_id),
            ),
        )
        if cur.rowcount:
            cur.execute(
                "SELECT type, document_id, status FROM jobs WHERE id = ?",
                (int(job_id),),
            )
            row = cur.fetchone()
            if row and row["type"] == "document.ingest" and row["document_id"]:
                projected = _DOC_STATUS.get(row["status"], row["status"])
                cur.execute(
                    """UPDATE documents
                       SET status = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (projected, int(row["document_id"])),
                )
        conn.commit()
    finally:
        conn.close()
    return get_job_row(job_id)


def update_progress(job_id: int, progress: int, message: str | None = None) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        if message is None:
            cur.execute(
                """UPDATE jobs
                   SET progress = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'running'""",
                (int(progress), int(job_id)),
            )
        else:
            cur.execute(
                """UPDATE jobs
                   SET progress = ?, message = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'running'""",
                (int(progress), message, int(job_id)),
            )
        conn.commit()
    finally:
        conn.close()


def append_event(job_id: int, kind: str, payload: dict) -> dict:
    body = dict(payload or {})
    body.setdefault("job_id", int(job_id))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM job_events WHERE job_id = ?", (int(job_id),))
        seq = int(cur.fetchone()["seq"]) + 1
        cur.execute(
            """INSERT INTO job_events (job_id, seq, kind, payload_json)
               VALUES (?, ?, ?, ?)""",
            (int(job_id), seq, kind, json.dumps(body, ensure_ascii=False)),
        )
        event_id = int(cur.lastrowid)
        progress = body.get("progress")
        message = body.get("message")
        if progress is not None or message:
            cur.execute(
                """UPDATE jobs
                   SET progress = COALESCE(?, progress),
                       message = COALESCE(?, message),
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status IN ('queued', 'running')""",
                (progress, message, int(job_id)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "id": event_id,
        "job_id": int(job_id),
        "seq": seq,
        "kind": kind,
        "payload": body,
    }


def list_events(job_id: int, after_seq: int = 0) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM job_events
               WHERE job_id = ? AND seq > ?
               ORDER BY seq ASC""",
            (int(job_id), int(after_seq)),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [public_event(row) for row in rows]


def project_document_status(document_id: int, job_status: str) -> None:
    status = _DOC_STATUS.get(job_status, job_status)
    conn = _connect()
    try:
        cur = conn.cursor()
        # chunk_count 由入库步骤自己写。这里只投影状态，避免把已留下的切片数清掉。
        cur.execute(
            """UPDATE documents
               SET status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, int(document_id)),
        )
        conn.commit()
    finally:
        conn.close()


def reconcile_after_restart() -> dict:
    """进程再启动时对账。

    入库和重建：interrupted / running 清掉半成品后回到 queued。
    生成：queued / running 改为 interrupted，不自动再调用模型。草稿保留。
    """
    from server.workers.document_worker import discard_partial_artifacts

    summary = {"generate_interrupted": 0, "ingest_requeued": 0, "reindex_requeued": 0}
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """SELECT id FROM jobs
               WHERE type = ? AND status IN ('queued', 'running')""",
            (GENERATE_TYPE,),
        )
        generate_ids = [int(row["id"]) for row in cur.fetchall()]
        if generate_ids:
            marks = ",".join("?" for _ in generate_ids)
            cur.execute(
                f"""UPDATE jobs
                    SET status = 'interrupted',
                        message = '进程退出，生成未继续',
                        finished_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({marks})""",
                generate_ids,
            )
            cur.execute(
                f"""UPDATE bid_versions
                    SET status = 'interrupted'
                    WHERE job_id IN ({marks}) AND status = 'draft'""",
                generate_ids,
            )
            summary["generate_interrupted"] = len(generate_ids)
        cur.execute(
            """SELECT id, type, document_id, payload_json FROM jobs
               WHERE type IN ('document.ingest', 'document.reindex')
                 AND status IN ('running', 'interrupted')"""
        )
        restart_rows = list(cur.fetchall())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for row in restart_rows:
        if row["type"] == "document.ingest" and row["document_id"]:
            doc_id = int(row["document_id"])
            try:
                discard_partial_artifacts(doc_id)
            except Exception:
                pass
            _mark_document_pending(doc_id)
            summary["ingest_requeued"] += 1
        else:
            _reopen_reindex_build(row["payload_json"])
            summary["reindex_requeued"] += 1
        _requeue_job(int(row["id"]))
    return summary


def _mark_document_pending(document_id: int) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE documents
               SET status = 'pending', chunk_count = 0, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (int(document_id),),
        )
        conn.commit()
    finally:
        conn.close()


def _requeue_job(job_id: int) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE jobs
               SET status = 'queued',
                   progress = 0,
                   message = '重启后继续',
                   cancel_requested = 0,
                   started_at = NULL,
                   finished_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (int(job_id),),
        )
        conn.commit()
    finally:
        conn.close()


def _reopen_reindex_build(payload_json: str | None) -> None:
    payload = _loads(payload_json, {})
    build_id = payload.get("build_id")
    if not build_id:
        return
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE index_builds
               SET status = 'building',
                   error = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status IN ('building', 'failed')""",
            (int(build_id),),
        )
        conn.commit()
    except Exception:
        return
    finally:
        conn.close()
