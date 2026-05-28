import sqlite3


DB_NAME = "quattro_ai.db"


def connect_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        role TEXT,
        content TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id TEXT PRIMARY KEY,
        mode TEXT DEFAULT 'assistant'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manager_id TEXT,
        manager_username TEXT,
        manager_first_name TEXT,
        client_name TEXT,
        event_date TEXT,
        event_format TEXT,
        guests_count TEXT,
        client_reaction TEXT,
        objections TEXT,
        next_step TEXT,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        executor_id TEXT,
        executor_username TEXT,
        executor_first_name TEXT,
        event_type TEXT,
        fact_guests TEXT,
        before_problems TEXT,
        during_problems TEXT,
        client_rating TEXT,
        what_went_well TEXT,
        what_to_improve TEXT,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT,
        first_name TEXT,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
