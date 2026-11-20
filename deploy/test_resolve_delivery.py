from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from telegram import Message

from database.db import Database
from deploy.resolve_delivery import resolve_delivery
from services.runtime import instance_lock


class DeliveryResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "assistant.sqlite3"
        self.database = Database(self.path)
        message = Message.de_json({
            "message_id": 1,
            "date": 1795170000,
            "chat": {"id": 42, "type": "private", "first_name": "Tester"},
            "from": {"id": 42, "is_bot": False, "first_name": "Tester"},
            "text": "Test note",
        }, None)
        self.database.accept(message, "note", 999)
        notification = self.database.claim_notification()
        self.notification_id = notification["id"]
        self.database.notification_result(notification, "uncertain", error="NetworkError")

    def resolve(self, **kwargs):
        return resolve_delivery(
            self.path, self.notification_id, expected_state="uncertain",
            operator="test-operator", reason="Telegram history checked", **kwargs,
        )

    def snapshot(self):
        with closing(self.database.connect()) as connection:
            outbox = [tuple(row) for row in connection.execute("SELECT * FROM assistant_outbox ORDER BY id")]
            audit = [tuple(row) for row in connection.execute("SELECT * FROM assistant_audit ORDER BY id")]
        return outbox, audit

    def test_confirmed_delivery_sets_sent_and_records_operator(self):
        self.assertEqual(self.resolve(sent_message_id=321), "sent")
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM assistant_outbox WHERE id=?", (self.notification_id,)).fetchone()
            audit = connection.execute("SELECT * FROM assistant_audit WHERE action='manual_delivery'").fetchone()
        self.assertEqual(row["state"], "sent")
        self.assertEqual(row["telegram_message_id"], 321)
        self.assertEqual(row["next_attempt"], 0)
        self.assertEqual(json.loads(audit["details"])["operator"], "test-operator")
        self.assertEqual(json.loads(audit["details"])["result"], "sent")

    def test_confirmed_non_delivery_requeues_one_record(self):
        self.assertEqual(self.resolve(confirmed_not_delivered=True), "pending")
        notification = self.database.claim_notification()
        self.assertEqual(notification["id"], self.notification_id)
        self.assertEqual(notification["next_attempt"], 0)
        self.assertIsNone(notification["telegram_message_id"])

    def test_missing_id_leaves_outbox_and_audit_unchanged(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            resolve_delivery(self.path, 999, expected_state="uncertain", operator="tester",
                             reason="checked", sent_message_id=321)
        self.assertEqual(self.snapshot(), before)

    def test_changed_state_cannot_be_resolved_twice(self):
        self.resolve(sent_message_id=321)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.resolve(confirmed_not_delivered=True)
        self.assertEqual(self.snapshot(), before)

    def test_audit_failure_rolls_back_delivery_change(self):
        with closing(self.database.connect()) as connection, connection:
            connection.execute("""
                CREATE TRIGGER reject_manual_audit BEFORE INSERT ON assistant_audit
                WHEN NEW.action='manual_delivery'
                BEGIN SELECT RAISE(ABORT, 'test audit failure'); END
            """)
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.resolve(sent_message_id=321)
        self.assertEqual(self.snapshot(), before)

    def test_active_instance_lock_prevents_resolution(self):
        before = self.snapshot()
        with instance_lock(self.path.parent / "assistant.lock"):
            with self.assertRaises(OSError):
                self.resolve(sent_message_id=321)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_action_leaves_data_unchanged(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.resolve(sent_message_id=321, confirmed_not_delivered=True)
        with self.assertRaises(ValueError):
            self.resolve(sent_message_id=-1)
        self.assertEqual(self.snapshot(), before)

    def test_unknown_schema_leaves_data_unchanged(self):
        with closing(self.database.connect()) as connection:
            connection.execute("PRAGMA user_version=2")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.resolve(sent_message_id=321)
        self.assertEqual(self.snapshot(), before)

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            resolve_delivery(missing, 1, expected_state="uncertain", operator="tester",
                             reason="checked", sent_message_id=321)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
