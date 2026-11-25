import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from telegram import Update, User
from telegram.error import Forbidden, NetworkError, RetryAfter
from telegram.ext import Application, ExtBot

import bot
from config import Settings
from database.db import Database, split_text
from services.ai import GPTUnavailable, generate_ai_response
from services.delivery import deliver_notifications
from services.runtime import instance_lock


def make_update(message_id=1, text="Заметка", user_id=42, chat_id=42, chat_type="private", command=None, edited=False, reply=False):
    chat = {"id": chat_id, "type": chat_type, "title": "Test group", "first_name": "Tester"}
    message = {
        "message_id": message_id,
        "date": 1795170000,
        "chat": chat,
        "from": {"id": user_id, "first_name": "Tester", "is_bot": False},
        "text": text,
    }
    if command:
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(command)}]
    if reply:
        message["reply_to_message"] = {
            "message_id": 99, "date": 1795170000, "chat": chat,
            "from": {"id": 123456, "first_name": "Quattro", "is_bot": True},
            "text": "Сообщение бота",
        }
    key = "edited_message" if edited else "message"
    return Update.de_json({"update_id": message_id, key: message}, None)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Database(Path(self.temp.name) / "test.sqlite3")

    def test_retry_and_concurrent_accept_create_one_record_and_notification(self):
        message = make_update().message
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.database.accept(message, "task", 999), range(2)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len(self.database.inbox()), 1)
        self.assertEqual(self.database.delivery_counts(), {"pending": 1})

    def test_concurrent_claim_has_one_owner(self):
        self.database.accept(make_update().message, "note", 999)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.database.claim_notification(), range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_restart_preserves_records_and_marks_in_flight_for_review(self):
        item, _ = self.database.accept(make_update().message, "task", 999)
        self.database.claim_notification()
        reopened = Database(self.database.path)
        reopened.recover_interrupted()
        self.assertEqual(reopened.notification_states(item["id"]), ["uncertain"])
        self.assertIsNone(reopened.claim_notification())
        self.assertEqual(len(reopened.inbox()), 1)

    def test_old_database_tables_are_preserved(self):
        with closing(self.database.connect()) as connection, connection:
            connection.execute("CREATE TABLE knowledge_notes (note TEXT)")
            connection.execute("INSERT INTO knowledge_notes VALUES ('historical')")
        Database(self.database.path)
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT note FROM knowledge_notes").fetchone()[0], "historical")

    def test_long_emoji_text_stays_within_telegram_limit(self):
        text = "Привет " + "🙂" * 3000
        parts = split_text(text)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 3500 for part in parts))

    def test_single_instance_lock_rejects_second_instance(self):
        path = Path(self.temp.name) / "runtime.lock"
        with instance_lock(path):
            with self.assertRaises(OSError):
                with instance_lock(path):
                    pass


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Database(Path(self.temp.name) / "test.sqlite3")
        self.item, _ = self.database.accept(make_update().message, "task", 999)
        self.sender = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)))

    async def test_success_is_not_repeated(self):
        await deliver_notifications(self.sender, self.database)
        await deliver_notifications(self.sender, self.database)
        self.assertEqual(self.sender.send_message.await_count, 1)
        self.assertEqual(self.database.notification_states(self.item["id"]), ["sent"])

    async def test_timeout_is_retained_without_blind_retry(self):
        self.sender.send_message.side_effect = NetworkError("timeout")
        await deliver_notifications(self.sender, self.database)
        await deliver_notifications(self.sender, self.database)
        self.assertEqual(self.sender.send_message.await_count, 1)
        self.assertEqual(self.database.notification_states(self.item["id"]), ["uncertain"])
        self.assertEqual(self.database.retry_failed(), 0)

    async def test_forbidden_is_saved_and_can_be_retried_by_owner(self):
        self.sender.send_message.side_effect = Forbidden("owner must start the bot")
        await deliver_notifications(self.sender, self.database)
        self.assertEqual(self.database.notification_states(self.item["id"]), ["failed"])
        self.sender.send_message.side_effect = None
        self.assertEqual(self.database.retry_failed(), 1)
        await deliver_notifications(self.sender, self.database)
        self.assertEqual(self.database.notification_states(self.item["id"]), ["sent"])

    async def test_rate_limit_defers_request(self):
        self.sender.send_message.side_effect = RetryAfter(30)
        await deliver_notifications(self.sender, self.database)
        self.assertEqual(self.database.notification_states(self.item["id"]), ["pending"])
        self.assertIsNone(self.database.claim_notification())

    async def test_saved_attachment_delivery_survives_deleted_source_and_has_no_duplicate(self):
        update = make_update(message_id=2)
        message = SimpleNamespace(
            from_user=update.message.from_user,
            chat_id=42, message_id=2, text=None, caption="Фото расстановки",
            photo=[SimpleNamespace(file_id="photo-id")],
        )
        item, _ = self.database.accept(message, "note", 999)
        self.sender.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=101))
        await deliver_notifications(self.sender, self.database, item["id"])
        await deliver_notifications(self.sender, self.database, item["id"])
        self.sender.send_photo.assert_awaited_once_with(chat_id=999, photo="photo-id")
        self.assertEqual(self.database.notification_states(item["id"]), ["sent", "sent"])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Database(Path(self.temp.name) / "test.sqlite3")
        self.settings = Settings(
            token="123456:offline-test-token", owner_id=999, data_dir=Path(self.temp.name),
            allowed_user_ids=frozenset({42, 43, 999}), allowed_chat_ids=frozenset({-10042}),
        )
        self.application = bot.build_application(self.settings, self.database)
        self.application._initialized = True
        object.__setattr__(self.application.bot, "_bot_user", User(123456, "Quattro", True, username="quattro_ai_assistant_bot"))
        self.messages = AsyncMock(return_value=SimpleNamespace(message_id=100))
        self.patch = patch.object(ExtBot, "send_message", self.messages)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.background_tasks = []

        def schedule(coroutine, **kwargs):
            task = asyncio.create_task(coroutine)
            self.background_tasks.append(task)
            return task

        self.schedule_patch = patch.object(Application, "create_task", side_effect=schedule)
        self.schedule_patch.start()
        self.addCleanup(self.schedule_patch.stop)

    async def emit(self, settle=True, **kwargs):
        update = make_update(**kwargs)
        if update.message:
            update.message.set_bot(self.application.bot)
        await self.application.process_update(update)
        if settle and self.background_tasks:
            await asyncio.gather(*self.background_tasks)

    async def test_plain_note_and_task_work_without_gpt(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock) as ai:
            await self.emit(text="Нужно пополнить запас воды")
            await self.emit(message_id=2, text="Задача Стасу согласовать смету")
            ai.assert_not_awaited()
        self.assertEqual([row["kind"] for row in self.database.inbox()], ["task", "note"])
        notifications = [call.kwargs for call in self.messages.await_args_list if call.kwargs.get("chat_id") == 999]
        self.assertEqual(len(notifications), 2)
        self.assertIn("Tester", notifications[0]["text"])

    async def test_groups_ignore_chatter_mentions_replies_edits_and_other_bots(self):
        for index, text in enumerate(["Обычная переписка", "@quattro_ai_assistant_bot привет", "Задача Стасу тест"]):
            await self.emit(message_id=index + 1, text=text, chat_id=-10042, chat_type="supergroup")
        await self.emit(message_id=5, text="/task test", command="/task", edited=True)
        await self.emit(message_id=6, text="/task@other_bot test", command="/task@other_bot", chat_id=-10042, chat_type="supergroup")
        await self.emit(message_id=7, text="Ответ боту", reply=True, chat_id=-10042, chat_type="group")
        await self.emit(message_id=8, text="/task без сущности команды", chat_id=-10042, chat_type="group")
        self.assertEqual(self.database.inbox(), [])
        self.messages.assert_not_awaited()

    async def test_group_commands_work_but_unknown_groups_and_users_are_blocked(self):
        await self.emit(text="/task@quattro_ai_assistant_bot Заказать воду", command="/task@quattro_ai_assistant_bot", chat_id=-10042, chat_type="supergroup")
        await self.emit(message_id=2, text="/task test", command="/task", chat_id=-10099, chat_type="group")
        await self.emit(message_id=3, text="Привет", user_id=88, chat_id=88)
        self.assertEqual(len(self.database.inbox()), 1)

    async def test_inbox_and_status_are_private_to_owner(self):
        await self.emit(text="Секретная заметка")
        self.messages.reset_mock()
        await self.emit(message_id=2, text="/inbox", command="/inbox", user_id=43, chat_id=43)
        await self.emit(message_id=3, text="/inbox", command="/inbox", user_id=999, chat_id=-10042, chat_type="supergroup")
        self.assertTrue(all("Секретная заметка" not in call.kwargs["text"] for call in self.messages.await_args_list))
        self.messages.reset_mock()
        await self.emit(message_id=4, text="/inbox", command="/inbox", user_id=999, chat_id=999)
        self.assertTrue(any("Секретная заметка" in call.kwargs["text"] for call in self.messages.await_args_list))

    async def test_gpt_error_does_not_block_following_note(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock, side_effect=GPTUnavailable):
            await self.emit(text="/gpt Вопрос", command="/gpt")
        await self.emit(message_id=2, text="Заметка после ошибки GPT")
        self.assertEqual(len(self.database.inbox()), 1)
        self.assertTrue(any("GPT сейчас недоступен" in call.kwargs["text"] for call in self.messages.await_args_list))

    async def test_slow_gpt_does_not_delay_saving_another_users_note(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_response(*args):
            started.set()
            await release.wait()
            return "Ответ"

        with patch.object(bot, "generate_ai_response", side_effect=slow_response):
            try:
                await self.emit(settle=False, text="/gpt Долгий вопрос", command="/gpt")
                await asyncio.wait_for(started.wait(), timeout=1)
                await asyncio.wait_for(self.emit(settle=False, message_id=2, text="Срочная заметка", user_id=43, chat_id=43), timeout=1)
                self.assertEqual(self.database.inbox()[0]["text"], "Срочная заметка")
                await self.emit(settle=False, message_id=3, text="/gpt Второй вопрос", command="/gpt")
                self.assertTrue(any("GPT занят" in call.kwargs["text"] for call in self.messages.await_args_list))
            finally:
                release.set()
                await asyncio.gather(*self.background_tasks)

    async def test_duplicate_gpt_update_reuses_answer_and_keeps_current_prompt_once(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock, return_value="Ответ") as ai:
            await self.emit(text="/gpt Вопрос", command="/gpt")
            await self.emit(text="/gpt Вопрос", command="/gpt")
            self.assertEqual(ai.await_count, 1)
            self.assertEqual(ai.await_args.args[1], "Вопрос")
            self.assertEqual(ai.await_args.args[2], [])

    async def test_gpt_in_group_does_not_receive_private_history(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock, return_value="Ответ") as ai:
            await self.emit(text="/gpt Личное", command="/gpt")
            await self.emit(message_id=2, text="/gpt Публичное", command="/gpt", chat_id=-10042, chat_type="supergroup")
            self.assertEqual(ai.await_args.args[2], [])

    async def test_private_gpt_history_excludes_group_conversation(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock, return_value="Ответ") as ai:
            await self.emit(text="/gpt Личное", command="/gpt")
            await self.emit(message_id=2, text="/gpt Публичное", command="/gpt", chat_id=-10042, chat_type="supergroup")
            await self.emit(message_id=3, text="/gpt Продолжение", command="/gpt")
            history = ai.await_args.args[2]
            self.assertEqual(len(history), 2)
            self.assertNotIn("Публичное", str(history))

    async def test_private_ai_history_excludes_other_user_and_failed_requests(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock, return_value="Ответ") as ai:
            await self.emit(text="/gpt Моё личное", command="/gpt")
            await self.emit(message_id=2, text="/gpt Чужое личное", command="/gpt", user_id=43, chat_id=43)
            ai.side_effect = GPTUnavailable
            await self.emit(message_id=3, text="/gpt Неуспешное", command="/gpt")
            ai.side_effect = None
            await self.emit(message_id=4, text="/gpt Продолжение", command="/gpt")
            self.assertEqual(ai.await_args.args[2], [
                {"role": "user", "content": "/gpt Моё личное"}, {"role": "assistant", "content": "Ответ"},
            ])

    async def test_disabled_ai_with_all_keys_saves_request_and_allows_next_note(self):
        self.application.bot_data["settings"] = replace(
            self.settings, ai_enabled=False, openai_key="offline-openai",
            deepseek_key="offline-deepseek", anthropic_key="offline-anthropic",
        )
        with patch("services.ai.AsyncOpenAI") as sdk, patch("services.ai.httpx.AsyncClient") as http:
            await self.emit(text="/gpt Вопрос", command="/gpt")
            sdk.assert_not_called()
            http.assert_not_called()
        await self.emit(message_id=2, text="Заметка при выключенном AI")
        self.assertEqual(len(self.database.inbox()), 1)
        self.assertEqual(self.database.ai_history(42, 999, chat_id=42), [])
        self.assertEqual(self.application.bot_data["gpt_active_users"], set())

    async def test_denied_users_and_groups_never_reach_ai(self):
        with patch.object(bot, "generate_ai_response", new_callable=AsyncMock) as ai:
            await self.emit(text="/gpt Вопрос", command="/gpt", user_id=88, chat_id=88)
            await self.emit(message_id=2, text="/gpt Вопрос", command="/gpt", chat_id=-10099, chat_type="group")
            ai.assert_not_awaited()

    async def test_status_reports_selected_ai_only_to_owner(self):
        self.application.bot_data["settings"] = replace(
            self.settings, ai_enabled=True, ai_provider="anthropic", anthropic_key="private-key",
        )
        await self.emit(text="/status", command="/status", user_id=999, chat_id=999)
        self.assertTrue(any("anthropic / claude-sonnet-4-6" in call.kwargs["text"] for call in self.messages.await_args_list))
        self.assertTrue(all("private-key" not in call.kwargs["text"] for call in self.messages.await_args_list))
        self.messages.reset_mock()
        await self.emit(message_id=2, text="/status", command="/status")
        await self.emit(message_id=3, text="/status", command="/status", user_id=999, chat_id=-10042, chat_type="group")
        self.messages.assert_not_awaited()

    async def test_menu_task_then_cancel_returns_to_notes(self):
        await self.emit(text="Задача Стасу")
        await self.emit(message_id=2, text="Согласовать договор")
        await self.emit(message_id=3, text="/cancel", command="/cancel")
        await self.emit(message_id=4, text="Наблюдение")
        self.assertEqual([row["kind"] for row in self.database.inbox()], ["note", "task"])


class GPTTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_fails_only_explicit_gpt_request(self):
        settings = Settings("token", 999, Path("unused"), ai_enabled=True, ai_provider="openai")
        with self.assertRaises(GPTUnavailable):
            await generate_ai_response(settings, "question", [])

    async def test_openai_request_uses_responses_and_no_shared_storage(self):
        settings = Settings("token", 999, Path("unused"), openai_key="offline",
                            ai_enabled=True, ai_provider="openai")
        response = SimpleNamespace(status="completed", output_text="Ответ GPT")
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response)))
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch("services.ai.AsyncOpenAI", return_value=manager):
            answer = await generate_ai_response(settings, "Новый вопрос", [])
        self.assertEqual(answer, "Ответ GPT")
        payload = client.responses.create.await_args.kwargs
        self.assertFalse(payload["store"])
        self.assertEqual(payload["input"], [{"role": "user", "content": "Новый вопрос"}])


if __name__ == "__main__":
    unittest.main()
