from database.db import connect_db


def set_user_mode(user_id, mode):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO user_settings (user_id, mode)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET mode = excluded.mode
        """,
        (str(user_id), mode)
    )

    conn.commit()
    conn.close()


def get_user_mode(user_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT mode
        FROM user_settings
        WHERE user_id = ?
        """,
        (str(user_id),)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0]

    return "assistant"
