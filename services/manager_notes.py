
from database.db import connect_db


def add_note(user, note):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO knowledge_notes (
            user_id,
            username,
            first_name,
            note
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            str(user.id),
            user.username or "",
            user.first_name or "",
            note,
        )
    )

    conn.commit()
    conn.close()


def get_last_notes(limit=10):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            created_at,
            first_name,
            username,
            note
        FROM knowledge_notes
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    return rows
