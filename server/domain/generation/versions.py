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
    columns = "id, project_name, strategy, generated_at, file_path, material_ids, project_id"
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
                  generated_at, file_path, material_ids, project_id
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
