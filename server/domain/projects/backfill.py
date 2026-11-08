"""把历史标书版本和报价收成项目。

规则（已确认决策 7）：
- ``bid_versions.project_name`` 全字相同的归为一个项目。
- 名称为空（NULL、空串、只有空白）的，每个版本各成一个项目。
- ``price_analyses.project_name`` 用同一个全字规则挂到已有项目上。
- 仅仅相似的名称不合并。对不上的报价保持 ``project_id`` 为空。
"""
import json
import sqlite3

def _is_blank(name) -> bool:
    return name is None or str(name).strip() == ""


def backfill_projects(conn: sqlite3.Connection) -> dict[str, int]:
    """只处理 ``project_id`` 仍为空的行。重复启动不会再合并一遍。"""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, project_name, parse_result_json, material_ids, generated_at
           FROM bid_versions
           WHERE project_id IS NULL
           ORDER BY id"""
    )
    versions = list(cur.fetchall())
    named: dict[str, list[sqlite3.Row]] = {}
    blanks: list[sqlite3.Row] = []
    for row in versions:
        if _is_blank(row["project_name"]):
            blanks.append(row)
        else:
            named.setdefault(str(row["project_name"]), []).append(row)

    created = 0
    for name, members in named.items():
        created += _attach_named_group(cur, name, members)
    for row in blanks:
        _create_for_version(cur, row)
        created += 1

    linked_prices = _link_prices(cur)
    linked_checks = _link_checklists(cur)
    return {
        "projects": created,
        "versions": len(versions),
        "prices": linked_prices,
        "checklists": linked_checks,
    }


def _attach_named_group(cur: sqlite3.Cursor, name: str, members: list[sqlite3.Row]) -> int:
    """把全字相同的版本挂到同一个项目。已有同名项目则沿用，不另起一个。"""
    cur.execute(
        "SELECT id, parse_id FROM projects WHERE name = ? ORDER BY id LIMIT 1",
        (name,),
    )
    existing = cur.fetchone()
    created = 0
    if existing is None:
        earliest = members[0]["generated_at"]
        cur.execute(
            """INSERT INTO projects
               (name, status, purchaser, deadline, created_by, parse_id,
                name_edited, deadline_edited, created_at, updated_at)
               VALUES (?, 'active', '', '', NULL, NULL, 1, 0,
                       COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)""",
            (name, earliest),
        )
        project_id = int(cur.lastrowid)
        created = 1
    else:
        project_id = int(existing["id"])

    for row in members:
        cur.execute(
            "UPDATE bid_versions SET project_id = ? WHERE id = ?",
            (project_id, row["id"]),
        )
    latest = max(members, key=lambda item: int(item["id"]))
    _copy_materials(cur, project_id, latest["material_ids"])
    _maybe_snapshot(cur, project_id, latest)
    return created


def _create_for_version(cur: sqlite3.Cursor, row: sqlite3.Row) -> None:
    cur.execute(
        """INSERT INTO projects
           (name, status, purchaser, deadline, created_by, parse_id,
            name_edited, deadline_edited, created_at, updated_at)
           VALUES ('', 'active', '', '', NULL, NULL, 0, 0,
                   COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)""",
        (row["generated_at"],),
    )
    project_id = int(cur.lastrowid)
    cur.execute(
        "UPDATE bid_versions SET project_id = ? WHERE id = ?",
        (project_id, row["id"]),
    )
    _copy_materials(cur, project_id, row["material_ids"])
    _maybe_snapshot(cur, project_id, row)


def _copy_materials(cur: sqlite3.Cursor, project_id: int, material_ids_json) -> None:
    try:
        raw = json.loads(material_ids_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(raw, list):
        return
    for item in raw:
        try:
            doc_id = int(item)
        except (TypeError, ValueError):
            continue
        cur.execute("SELECT id, scope FROM documents WHERE id = ?", (doc_id,))
        doc = cur.fetchone()
        if doc is None:
            continue
        scope = doc["scope"] or "library"
        if scope != "library":
            continue
        cur.execute(
            """INSERT OR IGNORE INTO project_documents (project_id, document_id, role)
               VALUES (?, ?, 'material')""",
            (project_id, doc_id),
        )


def _maybe_snapshot(cur: sqlite3.Cursor, project_id: int, version: sqlite3.Row) -> None:
    cur.execute(
        "SELECT parse_id, deadline, deadline_edited FROM projects WHERE id = ?",
        (project_id,),
    )
    project = cur.fetchone()
    if project is None or project["parse_id"]:
        return
    raw = version["parse_result_json"]
    if not raw or not str(raw).strip():
        return
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(parsed, dict):
        return
    cur.execute(
        """INSERT INTO parse_snapshots (project_id, document_id, result_json, job_id)
           VALUES (?, NULL, ?, NULL)""",
        (project_id, json.dumps(parsed, ensure_ascii=False)),
    )
    snap_id = int(cur.lastrowid)
    suggested = parsed.get("deadline")
    suggested_deadline = str(suggested).strip() if isinstance(suggested, str) else ""
    if not project["deadline_edited"] and not str(project["deadline"] or "").strip() and suggested_deadline:
        cur.execute(
            """UPDATE projects
               SET parse_id = ?, deadline = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (snap_id, suggested_deadline, project_id),
        )
    else:
        cur.execute(
            """UPDATE projects
               SET parse_id = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (snap_id, project_id),
        )


def _link_prices(cur: sqlite3.Cursor) -> int:
    cur.execute(
        "SELECT id, project_name FROM price_analyses WHERE project_id IS NULL"
    )
    linked = 0
    for row in cur.fetchall():
        if _is_blank(row["project_name"]):
            continue
        # 全字匹配。同名项目多于一个时挂到最早的那个，和版本分组同一条规则。
        cur.execute(
            "SELECT id FROM projects WHERE name = ? ORDER BY id LIMIT 1",
            (str(row["project_name"]),),
        )
        project = cur.fetchone()
        if project is None:
            continue
        cur.execute(
            "UPDATE price_analyses SET project_id = ? WHERE id = ?",
            (int(project["id"]), row["id"]),
        )
        linked += 1
    return linked


def _link_checklists(cur: sqlite3.Cursor) -> int:
    cur.execute(
        """SELECT c.id, c.bid_version_id, v.project_id
           FROM checklist_items c
           JOIN bid_versions v ON v.id = c.bid_version_id
           WHERE c.project_id IS NULL AND v.project_id IS NOT NULL"""
    )
    rows = list(cur.fetchall())
    for row in rows:
        cur.execute(
            """UPDATE checklist_items
               SET project_id = ?,
                   source_version_id = COALESCE(source_version_id, ?)
               WHERE id = ?""",
            (row["project_id"], row["bid_version_id"], row["id"]),
        )
    return len(rows)
