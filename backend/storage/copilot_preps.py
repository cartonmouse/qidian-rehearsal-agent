"""Copilot prep session persistence (SQLite)."""
import json
import sqlite3
from datetime import datetime

from backend.config import settings

DB_PATH = settings.db_path


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS copilot_preps (
            prep_id   TEXT PRIMARY KEY,
            user_id   TEXT NOT NULL,
            company   TEXT DEFAULT '',
            position  TEXT DEFAULT '',
            jd_text   TEXT DEFAULT '',
            status    TEXT NOT NULL DEFAULT 'running',
            progress  TEXT DEFAULT '',
            error     TEXT DEFAULT '',
            result    TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_copilot_preps_user ON copilot_preps(user_id)")
    conn.commit()
    return conn


def reset_stale_running(user_id: str | None = None):
    """Mark any 'running' preps as 'error' (called on server startup)."""
    conn = _get_conn()
    if user_id:
        conn.execute(
            "UPDATE copilot_preps SET status='error', error='Server restarted' WHERE status='running' AND user_id=?",
            (user_id,),
        )
    else:
        conn.execute(
            "UPDATE copilot_preps SET status='error', error='Server restarted' WHERE status='running'"
        )
    conn.commit()
    conn.close()


def create_prep(prep_id: str, user_id: str, company: str, position: str, jd_text: str):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO copilot_preps (prep_id, user_id, company, position, jd_text, status, progress, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'running', '初始化中...', ?)",
        (prep_id, user_id, company, position, jd_text[:200], datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def update_progress(prep_id: str, progress: str):
    conn = _get_conn()
    conn.execute("UPDATE copilot_preps SET progress=? WHERE prep_id=?", (progress, prep_id))
    conn.commit()
    conn.close()


def set_done(prep_id: str, result: dict):
    conn = _get_conn()
    conn.execute(
        "UPDATE copilot_preps SET status='done', progress='准备完成', result=? WHERE prep_id=?",
        (json.dumps(result, ensure_ascii=False), prep_id),
    )
    conn.commit()
    conn.close()


def set_error(prep_id: str, error: str):
    conn = _get_conn()
    conn.execute(
        "UPDATE copilot_preps SET status='error', error=? WHERE prep_id=?",
        (error, prep_id),
    )
    conn.commit()
    conn.close()


def get_prep(prep_id: str, user_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM copilot_preps WHERE prep_id=? AND user_id=?", (prep_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["result"] = json.loads(data["result"]) if data.get("result") else None
    return data


def list_preps(user_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT prep_id, company, position, jd_text, status, progress, created_at "
        "FROM copilot_preps WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_prep(prep_id: str, user_id: str) -> bool:
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM copilot_preps WHERE prep_id=? AND user_id=?", (prep_id, user_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
