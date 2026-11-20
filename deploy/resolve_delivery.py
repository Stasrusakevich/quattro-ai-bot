"""Resolve one uncertain delivery after an operator has checked Telegram."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.runtime import instance_lock


def resolve_delivery(database, notification_id, *, operator, reason,
                     expected_state, sent_message_id=None, confirmed_not_delivered=False):
    if notification_id <= 0 or expected_state != "uncertain":
        raise ValueError("A positive notification ID and expected state uncertain are required")
    if not operator.strip() or not reason.strip():
        raise ValueError("Operator and reason are required")
    if (sent_message_id is not None) == confirmed_not_delivered:
        raise ValueError("Choose a confirmed delivery ID or confirmed non-delivery")
    if sent_message_id is not None and sent_message_id <= 0:
        raise ValueError("Telegram message ID must be positive")

    database = Path(database).resolve(strict=True)
    if not database.is_file():
        raise ValueError("Database must be an existing file")
    state = "sent" if sent_message_id is not None else "pending"
    details = json.dumps({
        "notification_id": notification_id,
        "operator": operator.strip(),
        "reason": reason.strip(),
        "previous_state": expected_state,
        "result": state,
        "telegram_message_id": sent_message_id,
        "confirmed_not_delivered": confirmed_not_delivered,
    }, ensure_ascii=False)

    with instance_lock(database.parent / "assistant.lock"):
        with closing(sqlite3.connect(database.as_uri() + "?mode=rw", uri=True)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Unsupported database schema version")
                row = connection.execute(
                    "SELECT inbox_id, state FROM assistant_outbox WHERE id=?",
                    (notification_id,),
                ).fetchone()
                if row is None or row[1] != expected_state:
                    raise ValueError("Notification is missing or its state has changed")
                cursor = connection.execute("""
                    UPDATE assistant_outbox
                    SET state=?, telegram_message_id=?, error_type=NULL, next_attempt=0
                    WHERE id=? AND state=?
                """, (state, sent_message_id, notification_id, expected_state))
                if cursor.rowcount != 1:
                    raise ValueError("Notification state has changed")
                connection.execute("""
                    INSERT INTO assistant_audit (inbox_id, action, details, created_at)
                    VALUES (?, 'manual_delivery', ?, ?)
                """, (row[0], details, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("notification_id", type=int)
    parser.add_argument("--expected-state", choices=["uncertain"], required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    result = parser.add_mutually_exclusive_group(required=True)
    result.add_argument("--sent-message-id", type=int)
    result.add_argument("--confirmed-not-delivered", action="store_true")
    arguments = parser.parse_args()
    try:
        state = resolve_delivery(**vars(arguments))
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"Could not resolve delivery: {error}\n")
    print(f"Notification {arguments.notification_id}: {state}")


if __name__ == "__main__":
    main()
