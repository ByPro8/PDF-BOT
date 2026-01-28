import os
from datetime import datetime

import db

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")


def check_admin(pw):

    return pw == ADMIN_PASSWORD


def log(action, details=""):

    conn = db.db()

    conn.execute(
        """
        INSERT INTO admin_log(action, details, created_at)
        VALUES(?,?,?)
    """,
        (action, details, datetime.utcnow().isoformat()),
    )

    conn.commit()
    conn.close()
