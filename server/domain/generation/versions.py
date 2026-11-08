"""标书版本读写。新代码按 project_id 关联，project_name 仍留给旧页面和回填。"""
import difflib
import json
from typing import List, Optional

from fastapi import HTTPException

from server.db.sqlite import get_db

def list_bid_versions(project_name: Optional[str] = None, project_id: Optional[int] = None):
    """获取标书历史版本列表（按时间倒序）。传 project_id 时不再按名称模糊匹配。"""
    conn = get_db()
    cur = conn.cursor()
    columns = (
        "id, project_name, strategy, generated_at, file_path, material_ids, "
        "project_id, parse_id, status, job_id"
    )
    if project_id:
        cur.execute(
            f"""SELECT {columns}
               FROM bid_versions
               WHERE project_id = ?
               ORDER BY generated_at DESC""",
            (project_id,),
        )
    elif project_name:
        cur.execute(
            f"""SELECT {columns}
               FROM bid_versions
               WHERE project_name LIKE ?
               ORDER BY generated_at DESC""",
            (f"%{project_name}%",)
        )
    else:
        cur.execute(
            f"""SELECT {columns}
               FROM bid_versions
               ORDER BY generated_at DESC
               LIMIT 50"""
        )
    rows = cur.fetchall()
    conn.close()
    return {"versions": [dict(r) for r in rows]}


def get_bid_version(version_id: int):
    """获取指定版本详情"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, project_name, parse_result_json, bid_content, strategy,
                  generated_at, file_path, material_ids, project_id, parse_id,
                  status, outline_json, runtime_json, job_id
           FROM bid_versions WHERE id = ?""",
        (version_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")
    r = dict(row)
    # 反序列化 JSON 字段
    if r.get("parse_result_json"):
        r["parse_result"] = json.loads(r["parse_result_json"])
    else:
        r["parse_result"] = {}
    if r.get("material_ids"):
        r["material_ids"] = json.loads(r["material_ids"])
    else:
        r["material_ids"] = []
    return r


def compare_bid_versions(from_id: int, to_id: int):
    """对比两个版本的差异（简单行对比）"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, bid_content FROM bid_versions WHERE id IN (?, ?)",
        (from_id, to_id)
    )
    rows = {r["id"]: r for r in cur.fetchall()}
    conn.close()
    if from_id not in rows or to_id not in rows:
        raise HTTPException(status_code=404, detail="版本不存在")

    content_from = rows[from_id]["bid_content"] or ""
    content_to = rows[to_id]["bid_content"] or ""

    diff_lines = difflib.unified_diff(
        content_from.splitlines(keepends=True),
        content_to.splitlines(keepends=True),
        fromfile=f"v{from_id}",
        tofile=f"v{to_id}",
        lineterm=""
    )
    return {
        "from_id": from_id,
        "to_id": to_id,
        "diff_text": "".join(diff_lines),
    }


def restore_bid_version(version_id: int):
    """恢复指定版本：返回该版本的解析结果和素材ID，供前端重新生成"""
    version = get_bid_version(version_id)
    return {
        "parse_result": version.get("parse_result", {}),
        "material_ids": version.get("material_ids", []),
        "project_name": version.get("project_name", ""),
        "version_id": version_id,
    }


def insert_draft_version(
    *,
    project_name: str,
    parse_result: dict,
    strategy: str,
    material_ids: List[int],
    project_id: Optional[int] = None,
    parse_id: Optional[int] = None,
    outline: Optional[list] = None,
    runtime: Optional[dict] = None,
    job_id: Optional[int] = None,
) -> int:
    """生成一开始就落下 status=draft 的版本。正文先空着，章节边界再更新。"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO bid_versions
           (project_name, parse_result_json, bid_content, strategy, file_path,
            material_ids, project_id, parse_id, status, outline_json, runtime_json, job_id)
           VALUES (?, ?, '', ?, '', ?, ?, ?, 'draft', ?, ?, ?)""",
        (
            project_name,
            json.dumps(parse_result or {}, ensure_ascii=False),
            strategy or "",
            json.dumps(material_ids or [], ensure_ascii=False),
            project_id,
            parse_id,
            json.dumps(outline or [], ensure_ascii=False),
            json.dumps(runtime or {}, ensure_ascii=False),
            job_id,
        ),
    )
    conn.commit()
    version_id = int(cur.lastrowid)
    conn.close()
    return version_id


def update_draft_version(version_id: int, **fields) -> None:
    """按章节或收尾更新同一条草稿。未知字段忽略。"""
    allowed = {
        "bid_content": "bid_content",
        "status": "status",
        "file_path": "file_path",
        "strategy": "strategy",
    }
    assignments = []
    params: list = []
    for key, column in allowed.items():
        if key in fields and fields[key] is not None:
            assignments.append(f"{column} = ?")
            params.append(fields[key])
    if "material_ids" in fields and fields["material_ids"] is not None:
        assignments.append("material_ids = ?")
        params.append(json.dumps(fields["material_ids"], ensure_ascii=False))
    if not assignments:
        return
    params.append(int(version_id))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE bid_versions SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def discard_empty_draft(version_id: int) -> None:
    """预检失败时不留下空白版本。"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """DELETE FROM bid_versions
               WHERE id = ? AND status = 'draft'
                 AND (bid_content IS NULL OR bid_content = '')""",
            (int(version_id),),
        )
        conn.commit()
    finally:
        conn.close()


def _save_bid_version(
    project_name: str,
    parse_result: dict,
    bid_content: str,
    strategy: str,
    file_path: str,
    material_ids: List[int],
    project_id: Optional[int] = None,
):
    """将一次生成结果写入 bid_versions 表。选用的素材 id 抄在版本上。"""
    conn = get_db()
    cur = conn.cursor()
    linked_project = None
    if project_id:
        cur.execute("SELECT id, status FROM projects WHERE id = ?", (project_id,))
        linked_project = cur.fetchone()
        if linked_project is None:
            project_id = None
    cur.execute(
        """INSERT INTO bid_versions
           (project_name, parse_result_json, bid_content, strategy, file_path, material_ids, project_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            project_name,
            json.dumps(parse_result, ensure_ascii=False),
            bid_content,
            strategy,
            file_path,
            json.dumps(material_ids, ensure_ascii=False),
            project_id,
        )
    )
    if linked_project is not None and project_id:
        cur.execute(
            """UPDATE projects
               SET updated_at = CURRENT_TIMESTAMP,
                   status = CASE WHEN status = 'draft' THEN 'active' ELSE status END
               WHERE id = ?""",
            (project_id,),
        )
    conn.commit()
    version_id = cur.lastrowid
    conn.close()
    return version_id
