"""阶段 3：项目聚合、全字回填、解析快照、清单勾选和招标文件不进全局问答。"""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.api.auth import pwd_ctx
from server.db import sqlite as sqlite_mod
from server.domain.documents import files as files_mod
from server.domain.generation.materials import generation_material_ids
from server.domain.generation.versions import _save_bid_version, list_bid_versions
from server.domain.projects.service import list_projects

PASSWORD = "test-pass-123"


def _use_temp_db(monkeypatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sqlite_mod, "DB_PATH", data / "tender.db")
    monkeypatch.setattr(sqlite_mod, "DATA_DIR", data)
    monkeypatch.setattr(files_mod, "DATA_DIR", data)
    return data


def _cols(table: str) -> set[str]:
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _count(sql: str, params=()) -> int:
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def test_backfill_groups_exact_names_and_leaves_near_misses(monkeypatch, tmp_path):
    data = _use_temp_db(monkeypatch, tmp_path)
    db_path = data / "tender.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (2);

        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE bid_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            parse_result_json TEXT,
            bid_content TEXT,
            strategy TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            material_ids TEXT
        );

        CREATE TABLE price_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL DEFAULT '',
            formula_json TEXT NOT NULL DEFAULT '{}',
            cost_price REAL NOT NULL DEFAULT 0,
            suggested_price REAL,
            calculated_results TEXT NOT NULL DEFAULT '{}',
            strategy_scores TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_version_id INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT '其他',
            item TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待准备',
            remark TEXT DEFAULT '',
            source TEXT DEFAULT 'auto',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        """
    )
    conn.execute(
        """INSERT INTO documents (filename, file_type, file_path, file_size, status, chunk_count)
           VALUES ('hist.pdf', 'pdf', '/tmp/does-not-exist-tender-phase3.pdf', 10, 'ready', 1)"""
    )
    doc_id = int(conn.execute("SELECT id FROM documents").fetchone()[0])
    parse_a = json.dumps(
        {"project_name": "项目A", "deadline": "10天", "requirements": ["执照"]},
        ensure_ascii=False,
    )
    conn.execute(
        """INSERT INTO bid_versions (project_name, bid_content, strategy, material_ids)
           VALUES ('项目A', '第一版', '综合均衡型', '[]')"""
    )
    first_a = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """INSERT INTO bid_versions
           (project_name, parse_result_json, bid_content, strategy, material_ids)
           VALUES ('项目A', ?, '第二版', '技术优先型', ?)""",
        (parse_a, json.dumps([doc_id])),
    )
    conn.execute(
        """INSERT INTO bid_versions (project_name, bid_content, strategy)
           VALUES ('项目A ', '带空格', '综合均衡型')"""
    )
    conn.execute(
        """INSERT INTO bid_versions (project_name, bid_content, strategy)
           VALUES ('项目A二期', '仅仅相似', '综合均衡型')"""
    )
    conn.execute(
        """INSERT INTO bid_versions (project_name, bid_content, strategy)
           VALUES (NULL, '空名称', '综合均衡型')"""
    )
    conn.execute(
        """INSERT INTO bid_versions (project_name, bid_content, strategy)
           VALUES ('', '空字符串', '综合均衡型')"""
    )
    for name in ("项目A", "项目A ", "项目A二期", "项目B", "", "项目A二期 "):
        conn.execute(
            "INSERT INTO price_analyses (project_name, formula_json) VALUES (?, '{}')",
            (name,),
        )
    conn.execute(
        """INSERT INTO checklist_items (bid_version_id, category, item, status, source)
           VALUES (?, '盖章页', '投标函（加盖公章）', '已准备', 'auto')""",
        (first_a,),
    )
    conn.commit()
    conn.close()

    sqlite_mod.init_db()

    assert "project_id" in _cols("bid_versions")
    assert "project_id" in _cols("price_analyses")
    assert "source_version_id" in _cols("checklist_items")
    assert "job_id" in _cols("parse_snapshots")
    conn = sqlite_mod.get_db()
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    finally:
        conn.close()
    assert int(version) == 3

    conn = sqlite_mod.get_db()
    try:
        rows = conn.execute(
            "SELECT project_name, project_id FROM bid_versions ORDER BY id"
        ).fetchall()
        by_name = {}
        for row in rows:
            by_name.setdefault(row["project_name"], set()).add(row["project_id"])
        assert len(by_name["项目A"]) == 1
        assert by_name["项目A"] != by_name["项目A "]
        assert by_name["项目A"] != by_name["项目A二期"]
        assert len(by_name[None]) == 1
        assert len(by_name[""]) == 1
        assert by_name[None] != by_name[""]
        assert _count("SELECT COUNT(*) FROM projects") == 5

        project_a = conn.execute(
            "SELECT id FROM projects WHERE name = '项目A'"
        ).fetchone()["id"]
        price_a = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '项目A'"
        ).fetchone()["project_id"]
        price_space = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '项目A '"
        ).fetchone()["project_id"]
        price_similar = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '项目A二期'"
        ).fetchone()["project_id"]
        price_miss = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '项目B'"
        ).fetchone()["project_id"]
        price_blank = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = ''"
        ).fetchone()["project_id"]
        price_near = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '项目A二期 '"
        ).fetchone()["project_id"]
        assert price_a == project_a
        assert price_space == by_name["项目A "].pop()
        assert price_similar == by_name["项目A二期"].pop()
        assert price_miss is None
        assert price_blank is None
        assert price_near is None

        check = conn.execute(
            "SELECT project_id, source_version_id, status FROM checklist_items"
        ).fetchone()
        assert check["project_id"] == project_a
        assert check["source_version_id"] == first_a
        assert check["status"] == "已准备"

        project = conn.execute(
            "SELECT name_edited, deadline, parse_id FROM projects WHERE id = ?",
            (project_a,),
        ).fetchone()
        assert project["name_edited"] == 1
        assert project["deadline"] == "10天"
        assert project["parse_id"]
        snap = conn.execute(
            "SELECT result_json FROM parse_snapshots WHERE id = ?",
            (project["parse_id"],),
        ).fetchone()
        assert json.loads(snap["result_json"])["project_name"] == "项目A"
        linked_material = conn.execute(
            """SELECT document_id FROM project_documents
               WHERE project_id = ? AND role = 'material'""",
            (project_a,),
        ).fetchone()
        assert linked_material["document_id"] == doc_id
    finally:
        conn.close()

    listed = list_projects()
    unlinked_prices = {row["project_name"] for row in listed["unlinked"]["prices"]}
    assert "项目B" in unlinked_prices
    assert "" in unlinked_prices
    assert "项目A" not in unlinked_prices
    assert listed["unlinked"]["versions"] == []
    assert len(list_bid_versions()["versions"]) == 6

    before = _count("SELECT COUNT(*) FROM projects")
    sqlite_mod.init_db()
    assert _count("SELECT COUNT(*) FROM projects") == before


class _Generator:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def generate(self, prompt, system="", **kwargs):
        return json.dumps(self.payloads.pop(0), ensure_ascii=False)


def _parse_payload(name, deadline, extra=None):
    body = {
        "project_name": name,
        "deadline": deadline,
        "requirements": ["营业执照"],
        "qualification": ["ISO9001"],
        "scoring": {
            "method": "综合评分法",
            "total_score": 100,
            "sections": [{"name": "技术标", "weight": 100, "items": []}],
            "disqualify_conditions": [],
            "price_method": "lowest",
        },
    }
    if extra:
        body["requirements"] = extra
    return body


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "server.workers.executor.schedule_document",
        lambda *args, **kwargs: None,
    )
    import server.main as main_mod

    monkeypatch.setattr(main_mod, "_init_all_dbs", lambda: sqlite_mod.init_db())
    with TestClient(main_mod.app) as client:
        yield client


def _add_user(username: str) -> int:
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users (username, password_hash, role, must_change_password)
               VALUES (?, ?, 'user', 0)""",
            (username, pwd_ctx.hash(PASSWORD)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _login(client: TestClient, username: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_projects_are_shared_and_parse_snapshot_survives_refresh(api_client, monkeypatch, tmp_path):
    user_a = _add_user("phase3-a")
    user_b = _add_user("phase3-b")
    token_a = _login(api_client, "phase3-a")
    token_b = _login(api_client, "phase3-b")
    assert api_client.get("/api/projects").status_code == 401

    created = api_client.post("/api/projects", json={"name": ""}, headers=_auth(token_a))
    assert created.status_code == 200, created.text
    project = created.json()
    assert project["created_by"] == user_a
    assert project["name_edited"] is False
    project_id = project["id"]

    visible = api_client.get("/api/projects", headers=_auth(token_b))
    assert visible.status_code == 200
    assert project_id in {row["id"] for row in visible.json()["projects"]}

    generator = _Generator([
        _parse_payload("华北管道工程", "30天"),
        _parse_payload("另一个工程", "60天"),
    ])
    monkeypatch.setattr(
        "server.domain.generation.parse.get_generator",
        lambda: generator,
    )
    monkeypatch.setattr("server.domain.generation.parse.retrieve", lambda *args, **kwargs: [])

    tender = tmp_path / "tender.txt"
    tender.write_text("项目名称：华北管道工程\n" + ("招标正文" * 40), encoding="utf-8")
    uploaded = api_client.post(
        f"/api/projects/{project_id}/tender",
        files={"file": ("tender.txt", tender.read_bytes(), "text/plain")},
        headers=_auth(token_a),
    )
    assert uploaded.status_code == 200, uploaded.text
    document_id = uploaded.json()["document_id"]
    assert uploaded.json()["scope"] == "project"

    library = api_client.get("/api/kb/documents", headers=_auth(token_b))
    assert library.status_code == 200
    assert document_id not in {row["id"] for row in library.json()}

    parsed = api_client.post(
        "/api/bid/parse",
        json={"file_path": uploaded.json()["file_path"], "project_id": project_id},
        headers=_auth(token_a),
    )
    assert parsed.status_code == 200, parsed.text
    assert parsed.json()["project_name"] == "华北管道工程"
    conn = sqlite_mod.get_db()
    try:
        snap = conn.execute(
            "SELECT document_id FROM parse_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()
    assert snap["document_id"] == document_id

    renamed = api_client.put(
        f"/api/projects/{project_id}",
        json={"name": "用户改过的名字"},
        headers=_auth(token_a),
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "用户改过的名字"
    assert renamed.json()["name_edited"] is True

    again = api_client.post(
        "/api/bid/parse",
        json={"document_id": document_id, "project_id": project_id},
        headers=_auth(token_a),
    )
    assert again.status_code == 200, again.text
    assert again.json()["project_name"] == "用户改过的名字"
    assert again.json()["deadline"] == "60天"
    assert _count("SELECT COUNT(*) FROM parse_snapshots WHERE project_id = ?", (project_id,)) == 2

    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('material.pdf', 'pdf', 'library/m.pdf', 4, 'ready', 1, 'library', 'managed')"""
        )
        material_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    saved = api_client.put(
        f"/api/projects/{project_id}/materials",
        json={"document_ids": [material_id, document_id]},
        headers=_auth(token_a),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["material_ids"] == [material_id]

    refreshed = api_client.get(f"/api/projects/{project_id}", headers=_auth(token_b))
    body = refreshed.json()
    assert body["name"] == "用户改过的名字"
    assert body["deadline"] == "60天"
    assert body["parse"]["result"]["project_name"] == "用户改过的名字"
    assert body["parse"]["result"]["requirements"] == ["营业执照"]
    assert body["material_ids"] == [material_id]
    assert document_id in body["tender_document_ids"]

    rejected = api_client.post(
        f"/api/projects/{project_id}/documents",
        json={"document_id": material_id, "role": "tender"},
        headers=_auth(token_a),
    )
    assert rejected.status_code == 400
    rejected_material = api_client.post(
        f"/api/projects/{project_id}/documents",
        json={"document_id": document_id, "role": "material"},
        headers=_auth(token_a),
    )
    assert rejected_material.status_code == 400

    other = api_client.post("/api/projects", json={"name": "可归档"}, headers=_auth(token_b))
    archived = api_client.post(
        f"/api/projects/{other.json()['id']}/archive",
        headers=_auth(token_a),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert user_b != user_a


def test_file_path_parse_without_project_still_works(api_client, monkeypatch, tmp_path):
    _add_user("phase3-parse")
    token = _login(api_client, "phase3-parse")
    monkeypatch.setattr(
        "server.domain.generation.parse.get_generator",
        lambda: _Generator([_parse_payload("松散文件", "7天")]),
    )
    monkeypatch.setattr("server.domain.generation.parse.retrieve", lambda *args, **kwargs: [])
    loose = tmp_path / "loose.txt"
    loose.write_text("项目名称：松散文件\n" + ("正文" * 80), encoding="utf-8")
    resp = api_client.post(
        "/api/bid/parse",
        json={"file_path": str(loose)},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_name"] == "松散文件"
    assert _count("SELECT COUNT(*) FROM parse_snapshots") == 0


def test_checklist_checks_survive_a_new_version(api_client):
    _add_user("phase3-check")
    token = _login(api_client, "phase3-check")
    created = api_client.post("/api/projects", json={"name": "清单项目"}, headers=_auth(token))
    project_id = created.json()["id"]
    v1 = _save_bid_version("清单项目", {"project_name": "清单项目"}, "第一版正文", "综合均衡型", "", [], project_id)
    v2 = _save_bid_version("清单项目", {"project_name": "清单项目"}, "第二版正文", "综合均衡型", "", [], project_id)
    headers = _auth(token)

    first = api_client.post(
        "/api/checklist/generate",
        json={
            "bid_version_id": v1,
            "bid_content": "投标函",
            "parse_result": {"requirements": ["特殊资质甲"], "qualification": []},
        },
        headers=headers,
    )
    assert first.status_code == 200, first.text
    items = api_client.get(f"/api/checklist/{v1}", headers=headers).json()["items"]
    stamp = next(item for item in items if item["item"] == "投标函（加盖公章）")
    updated = api_client.put(
        f"/api/checklist/item/{stamp['id']}",
        json={"status": "已准备"},
        headers=headers,
    )
    assert updated.status_code == 200
    manual = api_client.post(
        "/api/checklist/item",
        json={"bid_version_id": v1, "category": "其他", "item": "自定义封套"},
        headers=headers,
    )
    assert manual.status_code == 200

    second = api_client.post(
        "/api/checklist/generate",
        json={
            "bid_version_id": v2,
            "bid_content": "投标函",
            "parse_result": {"requirements": ["特殊资质乙"], "qualification": []},
        },
        headers=headers,
    )
    assert second.status_code == 200, second.text
    again = api_client.get(f"/api/checklist/{v2}", headers=headers).json()["items"]
    kept = next(item for item in again if item["item"] == "投标函（加盖公章）")
    assert kept["status"] == "已准备"
    assert kept["source_version_id"] == v1
    assert kept["bid_version_id"] == v1
    assert kept["project_id"] == project_id
    assert any(item["item"] == "自定义封套" and item["source"] == "manual" for item in again)
    fresh = next(item for item in again if item["item"] == "特殊资质乙")
    assert fresh["source_version_id"] == v2
    assert fresh["status"] == "待准备"
    via_old = api_client.get(f"/api/checklist/{v1}", headers=headers).json()["items"]
    assert any(item["id"] == kept["id"] and item["status"] == "已准备" for item in via_old)

    # 没有项目的旧版本仍按该版本替换自动项。
    legacy = _save_bid_version("未挂项目", {}, "旧正文", "综合均衡型", "", [])
    api_client.post(
        "/api/checklist/generate",
        json={"bid_version_id": legacy, "bid_content": "投标函", "parse_result": {}},
        headers=headers,
    )
    legacy_items = api_client.get(f"/api/checklist/{legacy}", headers=headers).json()["items"]
    legacy_stamp = next(item for item in legacy_items if item["item"] == "投标函（加盖公章）")
    api_client.put(
        f"/api/checklist/item/{legacy_stamp['id']}",
        json={"status": "已准备"},
        headers=headers,
    )
    api_client.post(
        "/api/checklist/generate",
        json={"bid_version_id": legacy, "bid_content": "投标函", "parse_result": {}},
        headers=headers,
    )
    replaced = api_client.get(f"/api/checklist/{legacy}", headers=headers).json()["items"]
    replaced_stamp = next(item for item in replaced if item["item"] == "投标函（加盖公章）")
    assert replaced_stamp["status"] == "待准备"
    assert replaced_stamp["project_id"] is None


def test_global_retrieval_skips_project_tenders_but_explicit_ids_do_not(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    sqlite_mod.init_db()
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('lib.txt', 'txt', 'library/1.txt', 3, 'ready', 1, 'library', 'managed')"""
        )
        ready_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('pending.txt', 'txt', 'library/2.txt', 3, 'pending', 1, 'library', 'managed')"""
        )
        pending_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('tender.txt', 'txt', 'library/3.txt', 3, 'ready', 1, 'project', 'managed')"""
        )
        tender_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    from server.core.retriever import retriever

    chunks = [
        {"id": "c-ready", "text": "资料", "metadata": {"doc_id": ready_id}, "distance": 0.2},
        {"id": "c-pending", "text": "未就绪", "metadata": {"doc_id": pending_id}, "distance": 0.1},
        {"id": "c-tender", "text": "招标原文", "metadata": {"doc_id": tender_id}, "distance": 0.05},
    ]

    def fake_query(query, top_k=5, where=None):
        return list(chunks)

    monkeypatch.setattr(retriever, "query_chunks", fake_query)
    global_hits = retriever.retrieve("问题", top_k=5)
    assert [hit["doc_id"] for hit in global_hits] == [ready_id]
    project_hits = retriever.retrieve("问题", top_k=5, doc_ids=[tender_id])
    assert [hit["doc_id"] for hit in project_hits] == [tender_id]


def test_generation_can_read_this_projects_tender_chunks(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    sqlite_mod.init_db()
    conn = sqlite_mod.get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO projects (name, status) VALUES ('生成项目', 'active')"""
        )
        project_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO documents
               (filename, file_type, file_path, file_size, status, chunk_count, scope, storage)
               VALUES ('tender.txt', 'txt', 'library/t.txt', 3, 'ready', 1, 'project', 'managed')"""
        )
        tender_id = int(cur.lastrowid)
        cur.execute(
            """INSERT INTO project_documents (project_id, document_id, role)
               VALUES (?, ?, 'tender')""",
            (project_id, tender_id),
        )
        conn.commit()
    finally:
        conn.close()
    assert generation_material_ids([7], project_id) == [7, tender_id]
    assert generation_material_ids([7, tender_id], project_id) == [7, tender_id]
    assert generation_material_ids([7], None) == [7]


def test_price_links_by_exact_project_name(api_client):
    _add_user("phase3-price")
    token = _login(api_client, "phase3-price")
    created = api_client.post("/api/projects", json={"name": "报价项目"}, headers=_auth(token))
    project_id = created.json()["id"]
    saved = api_client.post(
        "/api/price/save",
        json={
            "project_name": "报价项目",
            "formula_json": "{}",
            "cost_price": 10,
            "suggested_price": 12,
        },
        headers=_auth(token),
    )
    assert saved.status_code == 200, saved.text
    missed = api_client.post(
        "/api/price/save",
        json={
            "project_name": "报价项目二期",
            "formula_json": "{}",
            "cost_price": 10,
            "suggested_price": 12,
        },
        headers=_auth(token),
    )
    assert missed.status_code == 200
    conn = sqlite_mod.get_db()
    try:
        linked = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '报价项目'"
        ).fetchone()["project_id"]
        unlinked = conn.execute(
            "SELECT project_id FROM price_analyses WHERE project_name = '报价项目二期'"
        ).fetchone()["project_id"]
    finally:
        conn.close()
    assert linked == project_id
    assert unlinked is None
    bundle = api_client.get(f"/api/projects/{project_id}", headers=_auth(token))
    assert bundle.json()["prices"][0]["project_id"] == project_id
    listed = api_client.get("/api/projects", headers=_auth(token)).json()
    assert any(row["project_name"] == "报价项目二期" for row in listed["unlinked"]["prices"])
