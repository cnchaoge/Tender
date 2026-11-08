"""
Tender - SQLite 数据库初始化
"""
import secrets
import sqlite3
from pathlib import Path

from passlib.context import CryptContext

from server.config import DATA_DIR, write_private_text

DB_PATH = DATA_DIR / "tender.db"

BOOTSTRAP_ADMIN_USERNAME = "admin"
BOOTSTRAP_DONE_KEY = "bootstrap_admin_done"
LEGACY_PASSWORD_CHECKED_KEY = "legacy_default_password_checked"
INITIAL_PASSWORD_FILENAME = "initial_admin_password.txt"
# Detected only so an existing install still using the old seeded password
# must change it. New installs never store this password.
LEGACY_ADMIN_PASSWORD = "admin123"

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cur = conn.cursor()

    # 用户表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 配置表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS configs (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # 文档表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 切片表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            metadata TEXT,
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # 操作日志
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 标书版本历史
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bid_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            parse_result_json TEXT,
            bid_content TEXT,
            strategy TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            material_ids TEXT
        )
    """)

    # 报价分析记录
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL DEFAULT '',
            formula_json TEXT NOT NULL DEFAULT '{}',
            cost_price REAL NOT NULL DEFAULT 0,
            suggested_price REAL,
            calculated_results TEXT NOT NULL DEFAULT '{}',
            strategy_scores TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 投标材料检查清单
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_version_id INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT '其他',
            item TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待准备',
            remark TEXT DEFAULT '',
            source TEXT DEFAULT 'auto',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 标书模板库
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bid_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            industry TEXT DEFAULT '',
            description TEXT DEFAULT '',
            chapters TEXT NOT NULL,
            default_strategy TEXT DEFAULT '综合均衡型',
            is_builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    _ensure_user_columns(cur)
    _ensure_document_columns(cur)
    _ensure_index_builds(cur)
    from server.domain.documents.files import backfill_document_storage

    managed, external = backfill_document_storage(conn)
    _ensure_content_hash_index(cur)
    initial_password_log = bootstrap_admin(conn, DATA_DIR)

    conn.commit()
    conn.close()
    print(f"[DB] SQLite initialized: {DB_PATH}")
    if managed or external:
        print(f"[DB] 文档原件归类：受管 {managed}，外部 {external}")
    if initial_password_log:
        print(initial_password_log)


def _config_get(cur: sqlite3.Cursor, key: str) -> str | None:
    cur.execute("SELECT value FROM configs WHERE key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return None
    return row["value"]


def _config_set(cur: sqlite3.Cursor, key: str, value: str) -> None:
    cur.execute(
        "INSERT INTO configs (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _ensure_document_columns(cur: sqlite3.Cursor) -> None:
    """阶段 2 加法列。已有库缺哪列补哪列，不换库。"""
    cur.execute("PRAGMA table_info(documents)")
    columns = {row[1] for row in cur.fetchall()}
    additions = (
        ("content_sha256", "TEXT"),
        ("scope", "TEXT NOT NULL DEFAULT 'library'"),
        ("storage", "TEXT NOT NULL DEFAULT 'external'"),
        ("extracted_relpath", "TEXT"),
    )
    for name, ddl in additions:
        if name not in columns:
            cur.execute(f"ALTER TABLE documents ADD COLUMN {name} {ddl}")


def _ensure_index_builds(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS index_builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            embed_provider TEXT NOT NULL,
            embed_model TEXT NOT NULL,
            dimension INTEGER,
            status TEXT NOT NULL,
            collection_name TEXT NOT NULL,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """
    )
    cur.execute("SELECT version FROM schema_version LIMIT 1")
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO schema_version (version) VALUES (2)")
    elif int(row["version"]) < 2:
        cur.execute("UPDATE schema_version SET version = 2")


def _ensure_content_hash_index(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_content_sha256
        ON documents(content_sha256)
        WHERE content_sha256 IS NOT NULL AND content_sha256 != ''
        """
    )


def _ensure_user_columns(cur: sqlite3.Cursor) -> None:
    cur.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cur.fetchall()}
    if "must_change_password" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN must_change_password "
            "INTEGER NOT NULL DEFAULT 0"
        )


def _parse_initial_password(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def _write_initial_password_file(path: Path, username: str, password: str) -> None:
    content = (
        f"username={username}\n"
        f"password={password}\n"
        "This one-time password was generated for the first install.\n"
        "Sign in and change it immediately, then delete this file.\n"
    )
    write_private_text(path, content)


def _flag_legacy_default_password(cur: sqlite3.Cursor) -> bool:
    """Require a password change if admin still uses the old public password.

    Returns True only when this call newly sets that requirement.
    """
    if _config_get(cur, LEGACY_PASSWORD_CHECKED_KEY) == "1":
        return False
    cur.execute(
        "SELECT id, password_hash, must_change_password FROM users WHERE username = ?",
        (BOOTSTRAP_ADMIN_USERNAME,),
    )
    row = cur.fetchone()
    if row is None or row["must_change_password"]:
        _config_set(cur, LEGACY_PASSWORD_CHECKED_KEY, "1")
        return False
    try:
        is_legacy = _pwd_ctx.verify(LEGACY_ADMIN_PASSWORD, row["password_hash"])
    except Exception:
        is_legacy = False
    if is_legacy:
        cur.execute(
            "UPDATE users SET must_change_password = 1 WHERE id = ?",
            (row["id"],),
        )
    _config_set(cur, LEGACY_PASSWORD_CHECKED_KEY, "1")
    return bool(is_legacy)


def bootstrap_admin(conn: sqlite3.Connection, data_dir: Path) -> str | None:
    """Create the first admin once, or flag the old public admin password.

    The returned string is a one-time log line containing a newly generated
    password. The caller must commit before printing it. Later startups, and
    a deleted admin user, do not create another account.
    """
    cur = conn.cursor()
    done = _config_get(cur, BOOTSTRAP_DONE_KEY)
    cur.execute("SELECT COUNT(*) AS n FROM users")
    user_count = int(cur.fetchone()["n"])

    if done == "1":
        _flag_legacy_default_password(cur)
        return None

    if user_count > 0:
        flagged = _flag_legacy_default_password(cur)
        _config_set(cur, BOOTSTRAP_DONE_KEY, "1")
        if flagged:
            print(
                "[auth] The admin account still uses the old public password. "
                "The next login must change it. The password was not reset."
            )
        else:
            print(
                "[auth] Existing users found. Skipped bootstrap admin creation. "
                "Deleting a user will not recreate admin."
            )
        return None

    path = data_dir / INITIAL_PASSWORD_FILENAME
    password = _parse_initial_password(path)
    generated = False
    if not password or password == LEGACY_ADMIN_PASSWORD:
        password = secrets.token_urlsafe(18)
        _write_initial_password_file(path, BOOTSTRAP_ADMIN_USERNAME, password)
        generated = True
    password_hash = _pwd_ctx.hash(password)
    cur.execute(
        "INSERT INTO users (username, password_hash, role, must_change_password) "
        "VALUES (?, ?, ?, 1)",
        (BOOTSTRAP_ADMIN_USERNAME, password_hash, "admin"),
    )
    _config_set(cur, BOOTSTRAP_DONE_KEY, "1")
    _config_set(cur, LEGACY_PASSWORD_CHECKED_KEY, "1")
    if not generated:
        print(
            "[auth] Created bootstrap admin from the existing one-time password "
            f"file {path}."
        )
        return None
    return (
        "[auth] Created bootstrap admin 'admin'. "
        f"One-time password file: {path}\n"
        f"[auth] Initial admin password (shown once): {password}\n"
        "[auth] Change this password at first login. "
        "It will not be printed again."
    )


if __name__ == "__main__":
    init_db()
