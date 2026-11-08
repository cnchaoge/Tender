"""项目聚合：创建、列表、归档、招标文件和素材引用、解析快照。

登录用户共用同一份列表。``created_by`` 只记录是谁创建的，查询不按人过滤。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from fastapi import HTTPException

from server.db.sqlite import get_db
from server.domain.documents.files import (
    move_into_library,
    relative_to_data,
    resolve_stored_path,
    sha256_file,
)

logger = logging.getLogger(__name__)

ROLE_TENDER = "tender"
ROLE_MATERIAL = "material"
ROLES = {ROLE_TENDER, ROLE_MATERIAL}
STATUSES = {"draft", "active", "archived"}
UNSET_NAMES = {"", "未识别到项目名称", "解析失败"}

_PROJECT_COLUMNS = """
    id, name, status, purchaser, deadline, created_by, parse_id,
    name_edited, deadline_edited, created_at, updated_at
"""


def _is_blank(name) -> bool:
    return name is None or str(name).strip() == ""


def _connect():
    return get_db()


def require_project(project_id: int) -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _project_row(row)


def _project_row(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"] or "",
        "status": row["status"] or "draft",
        "purchaser": row["purchaser"] or "",
        "deadline": row["deadline"] or "",
        "created_by": row["created_by"],
        "parse_id": row["parse_id"],
        "name_edited": bool(row["name_edited"]),
        "deadline_edited": bool(row["deadline_edited"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _touch(cur: sqlite3.Cursor, project_id: int) -> None:
    cur.execute(
        "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (project_id,),
    )


def create_project(
    name: str = "",
    purchaser: str = "",
    deadline: str = "",
    created_by: int | None = None,
) -> dict:
    cleaned = (name or "").strip()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO projects
               (name, status, purchaser, deadline, created_by, name_edited, deadline_edited)
               VALUES (?, 'draft', ?, ?, ?, ?, ?)""",
            (
                cleaned,
                (purchaser or "").strip(),
                (deadline or "").strip(),
                created_by,
                1 if cleaned else 0,
                1 if (deadline or "").strip() else 0,
            ),
        )
        project_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return get_project(project_id)


def list_projects() -> dict:
    """全部登录用户看到同一份项目。对不上的历史行单独列出。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT {_PROJECT_COLUMNS},
                       (SELECT COUNT(*) FROM bid_versions v WHERE v.project_id = projects.id) AS version_count,
                       (SELECT COUNT(*) FROM price_analyses a WHERE a.project_id = projects.id) AS price_count
                FROM projects
                ORDER BY updated_at DESC, id DESC"""
        )
        projects = []
        for row in cur.fetchall():
            item = _project_row(row)
            item["version_count"] = int(row["version_count"] or 0)
            item["price_count"] = int(row["price_count"] or 0)
            projects.append(item)
        cur.execute(
            """SELECT id, project_name, strategy, generated_at, file_path
               FROM bid_versions
               WHERE project_id IS NULL
               ORDER BY generated_at DESC, id DESC
               LIMIT 50"""
        )
        versions = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """SELECT id, project_name, cost_price, suggested_price, created_at
               FROM price_analyses
               WHERE project_id IS NULL
               ORDER BY created_at DESC, id DESC
               LIMIT 50"""
        )
        prices = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    return {"projects": projects, "unlinked": {"versions": versions, "prices": prices}}


def get_project(project_id: int) -> dict:
    project = require_project(project_id)
    conn = _connect()
    try:
        cur = conn.cursor()
        project["parse"] = _load_parse(cur, project.get("parse_id"))
        project["documents"] = _load_documents(cur, project_id)
        project["material_ids"] = [
            doc["document_id"] for doc in project["documents"] if doc["role"] == ROLE_MATERIAL
        ]
        project["tender_document_ids"] = [
            doc["document_id"] for doc in project["documents"] if doc["role"] == ROLE_TENDER
        ]
        cur.execute(
            """SELECT id, project_name, strategy, generated_at, file_path, material_ids, project_id
               FROM bid_versions
               WHERE project_id = ?
               ORDER BY generated_at DESC, id DESC
               LIMIT 50""",
            (project_id,),
        )
        project["versions"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """SELECT id, project_name, cost_price, suggested_price, created_at, project_id
               FROM price_analyses
               WHERE project_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT 20""",
            (project_id,),
        )
        project["prices"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """SELECT id, bid_version_id, project_id, source_version_id, category, item,
                      status, remark, source, sort_order, created_at
               FROM checklist_items
               WHERE project_id = ?
               ORDER BY sort_order ASC, id ASC""",
            (project_id,),
        )
        project["checklist_items"] = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    return project


def _load_parse(cur: sqlite3.Cursor, parse_id) -> dict | None:
    if not parse_id:
        return None
    cur.execute(
        """SELECT id, project_id, document_id, result_json, job_id, created_at
           FROM parse_snapshots WHERE id = ?""",
        (parse_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        result = json.loads(row["result_json"] or "{}")
    except json.JSONDecodeError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    return {
        "id": int(row["id"]),
        "project_id": int(row["project_id"]),
        "document_id": row["document_id"],
        "result": result,
        "job_id": row["job_id"],
        "created_at": row["created_at"],
    }


def _load_documents(cur: sqlite3.Cursor, project_id: int) -> list[dict]:
    cur.execute(
        """SELECT pd.document_id, pd.role, d.filename, d.file_type, d.status, d.scope
           FROM project_documents pd
           LEFT JOIN documents d ON d.id = pd.document_id
           WHERE pd.project_id = ?
           ORDER BY pd.id""",
        (project_id,),
    )
    docs = []
    for row in cur.fetchall():
        docs.append({
            "document_id": int(row["document_id"]),
            "role": row["role"],
            "filename": row["filename"] or "",
            "file_type": row["file_type"] or "",
            "status": row["status"] or "",
            "scope": row["scope"] or "",
        })
    return docs


def update_project(
    project_id: int,
    *,
    name: str | None = None,
    purchaser: str | None = None,
    deadline: str | None = None,
    status: str | None = None,
    name_set: bool = False,
    purchaser_set: bool = False,
    deadline_set: bool = False,
    status_set: bool = False,
) -> dict:
    require_project(project_id)
    if status_set and status not in STATUSES:
        raise HTTPException(status_code=400, detail="状态必须是 draft、active 或 archived")
    assignments = ["updated_at = CURRENT_TIMESTAMP"]
    params: list = []
    if name_set:
        assignments.append("name = ?")
        assignments.append("name_edited = 1")
        params.append((name or "").strip())
    if purchaser_set:
        assignments.append("purchaser = ?")
        params.append((purchaser or "").strip())
    if deadline_set:
        assignments.append("deadline = ?")
        assignments.append("deadline_edited = 1")
        params.append((deadline or "").strip())
    if status_set:
        assignments.append("status = ?")
        params.append(status)
    conn = _connect()
    try:
        cur = conn.cursor()
        params.append(project_id)
        cur.execute(
            f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()
    return get_project(project_id)


def archive_project(project_id: int) -> dict:
    return update_project(project_id, status="archived", status_set=True)


def _document_row(cur: sqlite3.Cursor, document_id: int) -> sqlite3.Row:
    cur.execute(
        "SELECT id, filename, file_path, scope, status, storage FROM documents WHERE id = ?",
        (document_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return row


def attach_document(project_id: int, document_id: int, role: str) -> dict:
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="role 只能是 tender 或 material")
    require_project(project_id)
    conn = _connect()
    try:
        cur = conn.cursor()
        doc = _document_row(cur, document_id)
        scope = doc["scope"] or "library"
        if role == ROLE_TENDER and scope != "project":
            raise HTTPException(status_code=400, detail="招标文件不能使用资料库文档")
        if role == ROLE_MATERIAL and scope != "library":
            raise HTTPException(status_code=400, detail="招标文件不作为公司素材")
        cur.execute(
            """INSERT OR IGNORE INTO project_documents (project_id, document_id, role)
               VALUES (?, ?, ?)""",
            (project_id, document_id, role),
        )
        _touch(cur, project_id)
        conn.commit()
    finally:
        conn.close()
    return get_project(project_id)


def set_materials(project_id: int, document_ids: list[int]) -> dict:
    require_project(project_id)
    cleaned: list[int] = []
    seen: set[int] = set()
    for raw in document_ids or []:
        try:
            doc_id = int(raw)
        except (TypeError, ValueError):
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        cleaned.append(doc_id)
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM project_documents WHERE project_id = ? AND role = ?",
            (project_id, ROLE_MATERIAL),
        )
        for doc_id in cleaned:
            cur.execute("SELECT id, scope FROM documents WHERE id = ?", (doc_id,))
            doc = cur.fetchone()
            if doc is None:
                continue
            if (doc["scope"] or "library") != "library":
                continue
            cur.execute(
                """INSERT OR IGNORE INTO project_documents (project_id, document_id, role)
                   VALUES (?, ?, 'material')""",
                (project_id, doc_id),
            )
        _touch(cur, project_id)
        conn.commit()
    finally:
        conn.close()
    project = get_project(project_id)
    return {"material_ids": project["material_ids"], "project": project}


def tender_document_ids(project_id: int) -> list[int]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT document_id FROM project_documents
               WHERE project_id = ? AND role = ?
               ORDER BY id""",
            (project_id, ROLE_TENDER),
        )
        return [int(row["document_id"]) for row in cur.fetchall()]
    finally:
        conn.close()


def _link_tender(cur: sqlite3.Cursor, project_id: int, document_id: int) -> None:
    doc = _document_row(cur, document_id)
    scope = doc["scope"] or "library"
    if scope != "project":
        return
    cur.execute(
        """INSERT OR IGNORE INTO project_documents (project_id, document_id, role)
           VALUES (?, ?, 'tender')""",
        (project_id, document_id),
    )


def record_parse_snapshot(project_id: int, document_id: int | None, result: dict) -> dict:
    """新解析写一条快照。用户改过的项目名和工期不被这次解析覆盖。"""
    project = require_project(project_id)
    stored = dict(result or {})
    new_name = None
    new_deadline = None
    if project["name_edited"]:
        stored["project_name"] = project["name"] or ""
    else:
        suggested = str(stored.get("project_name") or "").strip()
        if suggested not in UNSET_NAMES:
            new_name = suggested
            stored["project_name"] = suggested
    if project["deadline_edited"]:
        stored["deadline"] = project["deadline"] or ""
    else:
        suggested_deadline = str(stored.get("deadline") or "").strip()
        if suggested_deadline:
            new_deadline = suggested_deadline
            stored["deadline"] = suggested_deadline

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO parse_snapshots (project_id, document_id, result_json, job_id)
               VALUES (?, ?, ?, NULL)""",
            (
                project_id,
                document_id,
                json.dumps(stored, ensure_ascii=False),
            ),
        )
        snap_id = int(cur.lastrowid)
        assignments = ["parse_id = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list = [snap_id]
        if new_name is not None:
            assignments.append("name = ?")
            params.append(new_name)
        if new_deadline is not None:
            assignments.append("deadline = ?")
            params.append(new_deadline)
        params.append(project_id)
        cur.execute(
            f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        if document_id:
            _link_tender(cur, project_id, int(document_id))
        conn.commit()
    finally:
        conn.close()
    return stored


def update_current_snapshot(
    project_id: int,
    result: dict,
    *,
    name_edited: bool = False,
    deadline_edited: bool = False,
) -> dict:
    """把页面上的修改写回当前快照。没有快照时补一条，不另起一次解析。"""
    project = require_project(project_id)
    stored = dict(result or {})
    conn = _connect()
    try:
        cur = conn.cursor()
        assignments = ["updated_at = CURRENT_TIMESTAMP"]
        params: list = []
        if name_edited:
            name = str(stored.get("project_name") or "").strip()
            stored["project_name"] = name
            assignments.append("name = ?")
            assignments.append("name_edited = 1")
            params.append(name)
        elif not project["name_edited"] and _is_blank(project["name"]):
            suggested = str(stored.get("project_name") or "").strip()
            if suggested not in UNSET_NAMES:
                stored["project_name"] = suggested
                assignments.append("name = ?")
                params.append(suggested)
        if deadline_edited:
            deadline = str(stored.get("deadline") or "").strip()
            stored["deadline"] = deadline
            assignments.append("deadline = ?")
            assignments.append("deadline_edited = 1")
            params.append(deadline)
        payload = json.dumps(stored, ensure_ascii=False)
        if project["parse_id"]:
            cur.execute(
                "UPDATE parse_snapshots SET result_json = ? WHERE id = ?",
                (payload, project["parse_id"]),
            )
        else:
            cur.execute(
                """INSERT INTO parse_snapshots (project_id, document_id, result_json, job_id)
                   VALUES (?, NULL, ?, NULL)""",
                (project_id, payload),
            )
            assignments.append("parse_id = ?")
            params.append(int(cur.lastrowid))
        params.append(project_id)
        cur.execute(
            f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()
    return get_project(project_id)


def link_price_project(explicit_id: int | None, project_name: str) -> tuple[int | None, str]:
    """保存报价时写入 project_id。未指定 id 时只按全字相同的项目名挂接。"""
    if explicit_id:
        project = require_project(int(explicit_id))
        name = project_name if not _is_blank(project_name) else project["name"]
        return int(explicit_id), name or ""
    if _is_blank(project_name):
        return None, project_name or ""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM projects WHERE name = ? ORDER BY id LIMIT 1",
            (str(project_name),),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None, project_name
    return int(row["id"]), project_name


def _lookup_hash(cur: sqlite3.Cursor, digest: str) -> sqlite3.Row | None:
    cur.execute(
        """SELECT id, filename, file_path, scope, status, storage
           FROM documents
           WHERE content_sha256 = ?
           ORDER BY id
           LIMIT 1""",
        (digest,),
    )
    return cur.fetchone()


def store_tender_file(project_id: int, filename: str, source: Path, file_type: str) -> dict:
    """招标文件以 scope=project 入库，并挂到项目上。不改成资料库文档。"""
    require_project(project_id)
    digest = sha256_file(source)
    size = source.stat().st_size
    suffix = source.suffix.lower()
    conn = _connect()
    try:
        cur = conn.cursor()
        existing = _lookup_hash(cur, digest)
        if existing is not None and (existing["scope"] or "") == "system":
            source.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="不能把内置术语表当作招标文件")
        if existing is not None:
            document_id = int(existing["id"])
            stored_name = existing["filename"] or filename
            status = existing["status"] or "ready"
            file_path = str(resolve_stored_path(existing["file_path"]))
            scope = existing["scope"] or "library"
            source.unlink(missing_ok=True)
        else:
            cur.execute(
                """INSERT INTO documents
                   (filename, file_type, file_path, file_size, status, chunk_count,
                    scope, storage, content_sha256)
                   VALUES (?, ?, '', ?, 'pending', 0, 'project', 'managed', ?)""",
                (filename, file_type, size, digest),
            )
            document_id = int(cur.lastrowid)
            conn.commit()
            try:
                dest = move_into_library(document_id, source, suffix or ".bin")
            except Exception:
                cur.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                conn.commit()
                source.unlink(missing_ok=True)
                raise
            rel = relative_to_data(dest)
            cur.execute(
                """UPDATE documents
                   SET file_path = ?, file_size = ?, storage = 'managed', scope = 'project',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (rel, size, document_id),
            )
            stored_name = filename
            status = "pending"
            file_path = str(dest)
            scope = "project"
            _schedule_tender(document_id, str(dest))
        cur.execute(
            """INSERT OR IGNORE INTO project_documents (project_id, document_id, role)
               VALUES (?, ?, 'tender')""",
            (project_id, document_id),
        )
        _touch(cur, project_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "document_id": document_id,
        "filename": stored_name,
        "file_path": file_path,
        "status": status,
        "project_id": project_id,
        "scope": scope,
    }


def _schedule_tender(document_id: int, file_path: str) -> None:
    """沿用现有入库线程。失败时留下原件，解析不依赖向量化完成。"""
    try:
        from server.workers.executor import schedule_document

        schedule_document(document_id, file_path)
    except Exception:
        logger.exception("failed to schedule tender doc_id=%s", document_id)
