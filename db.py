import sqlite3
from pathlib import Path
from datetime import datetime
import os

BASE = Path(__file__).parent

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE / "data")))
DB_PATH = DATA_DIR / "checks.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            template_hash TEXT NOT NULL,
            filename TEXT,
            stored_path TEXT,
            created_at TEXT NOT NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON checks(template_hash)")

    conn.commit()
    conn.close()


# -------- Queries --------


def get_matches(template_hash):

    conn = db()

    rows = conn.execute(
        """
        SELECT id, filename
        FROM checks
        WHERE template_hash=?
    """,
        (template_hash,),
    ).fetchall()

    conn.close()

    return [dict(r) for r in rows]


def add_record(label, template_hash, filename, path):

    conn = db()

    conn.execute(
        """
        INSERT INTO checks(label, template_hash, filename, stored_path, created_at)
        VALUES(?,?,?,?,?)
    """,
        (label, template_hash, filename, path, datetime.utcnow().isoformat()),
    )

    conn.commit()
    conn.close()


def find_by_filename(name):

    if not name:
        return None

    conn = db()

    row = conn.execute(
        """
        SELECT id, filename, label
        FROM checks
        WHERE lower(filename)=lower(?)
        LIMIT 1
    """,
        (name.strip(),),
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def list_files():

    conn = db()

    rows = conn.execute(
        """
        SELECT id, label, filename, created_at
        FROM checks
        ORDER BY id DESC
    """
    ).fetchall()

    conn.close()

    return [dict(r) for r in rows]


def search_files(q):

    conn = db()

    rows = conn.execute(
        """
        SELECT id, label, filename, created_at
        FROM checks
        WHERE filename LIKE ?
        ORDER BY id DESC
    """,
        (f"%{q}%",),
    ).fetchall()

    conn.close()

    return [dict(r) for r in rows]


def get_file_path(file_id):

    conn = db()

    row = conn.execute(
        """
        SELECT stored_path FROM checks WHERE id=?
    """,
        (file_id,),
    ).fetchone()

    conn.close()

    return row["stored_path"] if row else None


def delete_record(file_id):

    conn = db()

    conn.execute("DELETE FROM checks WHERE id=?", (file_id,))

    conn.commit()
    conn.close()


def update_label(file_id: int, label: str) -> bool:

    conn = db()

    cur = conn.execute(
        "UPDATE checks SET label=? WHERE id=?",
        (label, file_id),
    )

    conn.commit()
    conn.close()

    return cur.rowcount > 0


def reset_db():

    if DB_PATH.exists():
        DB_PATH.unlink()

    init_db()
