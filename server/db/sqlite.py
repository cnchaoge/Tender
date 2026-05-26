"""
Tender - SQLite 数据库初始化
"""
import sqlite3
from pathlib import Path
from server.config import DATA_DIR

DB_PATH = DATA_DIR / "tender.db"


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

    # 默认管理员账号 admin / admin123
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    password_hash = pwd_ctx.hash("admin123")
    try:
        cur.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", password_hash, "admin")
        )
    except Exception:
        pass

    conn.commit()
    conn.close()
    print(f"[DB] SQLite initialized: {DB_PATH}")


if __name__ == "__main__":
    init_db()
