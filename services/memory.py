from database.db import connect_db


def save_message(user_id, role, content):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO messages (user_id, role, content)
        VALUES (?, ?, ?)
        """,
        (str(user_id), role, content)
    )

    conn.commit()
    conn.close()


def get_conversation(user_id, limit=10):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(user_id), limit)
    )

    rows = cursor.fetchall()
    conn.close()

    rows.reverse()

    return [
        {
            "role": row[0],
            "content": row[1]
        }
        for row in rows
    ]


def clear_conversation(user_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM messages
        WHERE user_id = ?
        """,
        (str(user_id),)
    )

    conn.commit()
    conn.close()
