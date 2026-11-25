import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from config import ROOT, Settings, load_settings
from services import ai


PROVIDERS = ("deepseek", "openai", "anthropic")
KEYS = {"deepseek": "deepseek-test-key", "openai": "openai-test-key", "anthropic": "anthropic-test-key"}
HISTORY = [{"role": "user", "content": "Прошлый вопрос"}, {"role": "assistant", "content": "Прошлый ответ"}]
HTTP_CLIENT = httpx.AsyncClient


def settings_for(provider, **changes):
    settings = Settings(
        "offline-token", 999, Path("unused"), ai_enabled=True, ai_provider=provider,
        openai_key=KEYS["openai"], deepseek_key=KEYS["deepseek"], anthropic_key=KEYS["anthropic"],
    )
    return replace(settings, **changes)


def successful_body(provider):
    if provider == "openai":
        return {
            "id": "resp_test", "object": "response", "created_at": 1, "model": "test-model",
            "status": "completed", "output": [{"type": "message", "id": "msg_test", "role": "assistant",
                "status": "completed", "content": [{"type": "output_text", "text": " Ответ ", "annotations": []}]}],
        }
    if provider == "deepseek":
        return {"id": "test", "object": "chat.completion", "created": 1, "model": "test-model",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": " Ответ "}}]}
    return {"id": "msg_test", "type": "message", "role": "assistant", "stop_reason": "end_turn",
            "content": [{"type": "text", "text": " Ответ "}]}


class SettingsTests(unittest.TestCase):
    def load(self, **env):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "offline-token", "ADMIN_USER_ID": "999", **env}, clear=True), \
                patch("config.load_dotenv"):
            return load_settings()

    def test_default_is_disabled_deepseek_flash_even_with_old_openai_key(self):
        settings = self.load(OPENAI_API_KEY="old-key", OPENAI_MODEL="old-model")
        self.assertFalse(settings.ai_enabled)
        self.assertEqual(settings.ai_provider, "deepseek")
        self.assertEqual(settings.ai_model_id, "deepseek-flash")
        self.assertEqual(settings.ai_key, "")

    def test_enabled_values_are_explicit_and_fail_closed(self):
        for value in ("", "false", "0", "1", "yes", "tru", "enabled"):
            with self.subTest(value=value):
                self.assertFalse(self.load(AI_ENABLED=value).ai_enabled)
        self.assertTrue(self.load(AI_ENABLED=" True ").ai_enabled)

    def test_provider_and_model_switch_and_key_selection_from_env(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                settings = self.load(AI_ENABLED="true", AI_PROVIDER=f" {provider.upper()} ", AI_MODEL=" custom-model ",
                                     OPENAI_API_KEY=KEYS["openai"], ANTHROPIC_API_KEY=KEYS["anthropic"],
                                     DEEPSEEK_API_KEY=KEYS["deepseek"])
                self.assertEqual(settings.ai_provider, provider)
                self.assertEqual(settings.ai_model_id, "custom-model")
                self.assertEqual(settings.ai_key, KEYS[provider])

    def test_legacy_openai_model_is_used_only_for_openai_without_ai_model(self):
        for provider, expected in (("openai", "legacy-gpt"), ("deepseek", "deepseek-flash"), ("anthropic", "claude-sonnet-4-6")):
            with self.subTest(provider=provider):
                self.assertEqual(self.load(AI_PROVIDER=provider, OPENAI_MODEL="legacy-gpt").ai_model_id, expected)
        self.assertEqual(self.load(AI_PROVIDER="openai", OPENAI_MODEL="legacy", AI_MODEL="explicit").ai_model_id, "explicit")

    def test_dotenv_load_preserves_process_environment_and_access_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "AI_ENABLED=true\nAI_PROVIDER=anthropic\nAI_MODEL=from-dotenv\nANTHROPIC_API_KEY=dotenv-key\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "offline", "ADMIN_USER_ID": "999",
                                         "ALLOWED_USER_IDS": "42,43", "ALLOWED_CHAT_IDS": "-10042", "AI_ENABLED": "false"}, clear=True), \
                    patch("config.ROOT", root):
                settings = load_settings()
        self.assertFalse(settings.ai_enabled)
        self.assertEqual(settings.ai_provider, "anthropic")
        self.assertEqual(settings.ai_model_id, "from-dotenv")
        self.assertEqual(settings.ai_key, "dotenv-key")
        self.assertEqual(settings.allowed_user_ids, frozenset({42, 43, 999}))
        self.assertEqual(settings.allowed_chat_ids, frozenset({-10042}))

    def test_status_uses_active_provider_and_never_contains_keys(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                settings = settings_for(provider)
                status = ai.ai_status(settings)
                self.assertIn(provider, status)
                self.assertIn(settings.ai_model_id, status)
                for key in KEYS.values():
                    self.assertNotIn(key, status)
                    self.assertNotIn(key, repr(settings))
                key_field = {"openai": "openai_key", "deepseek": "deepseek_key", "anthropic": "anthropic_key"}[provider]
                self.assertIn(settings.ai_key_name, ai.ai_status(replace(settings, **{key_field: ""})))
        self.assertIn("выключен", ai.ai_status(settings_for("deepseek", ai_enabled=False)))
        self.assertIn("неизвестный", ai.ai_status(settings_for("unknown")))


class ConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def call_provider(self, provider, body=None, *, status=200, failure=None, **settings_changes):
        self.requests = []
        self.sdk_options = []
        self.http_options = []

        async def handler(request):
            self.requests.append(request)
            if failure is not None:
                raise failure
            return httpx.Response(status, json=body if body is not None else successful_body(provider))

        transport = httpx.MockTransport(handler)

        def sdk_client(**kwargs):
            self.sdk_options.append(kwargs)
            return AsyncOpenAI(**kwargs, http_client=HTTP_CLIENT(transport=transport))

        def http_client(**kwargs):
            self.http_options.append(kwargs)
            return HTTP_CLIENT(**kwargs, transport=transport)

        # Exercise the real SDK serialization/deserialization with an in-memory transport.
        # The unused adapter constructor must never be called, including on errors.
        if provider == "anthropic":
            with patch("services.ai.httpx.AsyncClient", side_effect=http_client), \
                    patch("services.ai.AsyncOpenAI") as unused:
                try:
                    return await ai.generate_ai_response(settings_for(provider, **settings_changes), "Новый вопрос", HISTORY)
                finally:
                    unused.assert_not_called()
        with patch("services.ai.AsyncOpenAI", side_effect=sdk_client):
            return await ai.generate_ai_response(settings_for(provider, **settings_changes), "Новый вопрос", HISTORY)

    async def test_each_wire_request_preserves_instructions_history_and_uses_own_key(self):
        instructions = (ROOT / "prompts/system_prompt.txt").read_text(encoding="utf-8")
        instructions += "\n\nСправка Quattro\n" + (ROOT / "knowledge/assistant.md").read_text(encoding="utf-8")
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                answer = await self.call_provider(provider, ai_model="custom-model")
                self.assertEqual(answer, "Ответ")
                self.assertEqual(len(self.requests), 1)
                request = self.requests[0]
                self.assertEqual(request.method, "POST")
                payload = json.loads(request.content)
                self.assertEqual(payload["model"], "custom-model")
                messages = [*HISTORY, {"role": "user", "content": "Новый вопрос"}]
                if provider == "openai":
                    self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
                    self.assertEqual(payload["instructions"], instructions)
                    self.assertEqual(payload["input"], messages)
                    self.assertFalse(payload["store"])
                    self.assertEqual(payload["max_output_tokens"], 2000)
                elif provider == "deepseek":
                    self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
                    self.assertEqual(payload["messages"], [{"role": "system", "content": instructions}, *messages])
                    self.assertEqual(payload["thinking"], {"type": "disabled"})
                    self.assertEqual(payload["max_tokens"], 2000)
                else:
                    self.assertEqual(str(request.url), "https://api.anthropic.com/v1/messages")
                    self.assertEqual(payload["system"], instructions)
                    self.assertEqual(payload["messages"], messages)
                    self.assertEqual(payload["max_tokens"], 2000)
                    self.assertEqual(request.headers["anthropic-version"], "2026-10-21")
                    self.assertEqual(self.http_options, [{"timeout": 45, "follow_redirects": False}])
                header = "x-api-key" if provider == "anthropic" else "authorization"
                prefix = "" if provider == "anthropic" else "Bearer "
                self.assertEqual(request.headers[header], prefix + KEYS[provider])
                for other in set(PROVIDERS) - {provider}:
                    self.assertNotIn(KEYS[other], str(request.headers) + request.content.decode())
                if provider != "anthropic":
                    self.assertEqual(self.sdk_options[0]["max_retries"], 0)
                    self.assertEqual(self.sdk_options[0]["timeout"], 45)
        self.assertEqual(len(HISTORY), 2)

    async def test_default_deepseek_wire_model_is_official_flash_id(self):
        await self.call_provider("deepseek")
        self.assertEqual(json.loads(self.requests[0].content)["model"], "deepseek-flash")

    async def test_disabled_unknown_provider_and_missing_selected_key_never_create_clients(self):
        cases = [settings_for(p, ai_enabled=False) for p in PROVIDERS]
        cases.append(settings_for("unknown"))
        for provider in PROVIDERS:
            field = {"deepseek": "deepseek_key", "openai": "openai_key", "anthropic": "anthropic_key"}[provider]
            cases.append(settings_for(provider, **{field: ""}))
        for settings in cases:
            with self.subTest(provider=settings.ai_provider, enabled=settings.ai_enabled), \
                    patch("services.ai.AsyncOpenAI") as sdk, patch("services.ai.httpx.AsyncClient") as http:
                with self.assertRaises(ai.AIUnavailable):
                    await ai.generate_ai_response(settings, "secret question", [])
                sdk.assert_not_called()
                http.assert_not_called()

    async def test_http_errors_do_not_retry_fallback_or_expose_bodies(self):
        for provider in PROVIDERS:
            for status in (401, 429, 500, 503):
                with self.subTest(provider=provider, status=status):
                    with self.assertRaises(ai.AIUnavailable) as error:
                        await self.call_provider(provider, {"error": {"message": "sensitive corporate body " + KEYS[provider]}}, status=status)
                    self.assertEqual(len(self.requests), 1)
                    self.assertEqual(str(error.exception), "AI provider request failed")

    async def test_network_errors_and_timeouts_are_sanitized_and_not_retried(self):
        for provider in PROVIDERS:
            for failure in (httpx.ReadTimeout("sensitive body"), httpx.ConnectError("sensitive body")):
                with self.subTest(provider=provider, failure=type(failure).__name__):
                    with self.assertRaises(ai.AIUnavailable) as error:
                        await self.call_provider(provider, failure=failure)
                    self.assertEqual(len(self.requests), 1)
                    self.assertNotIn("sensitive", str(error.exception))

    async def test_empty_truncated_refused_and_malformed_answers_are_rejected(self):
        for provider in PROVIDERS:
            bodies = [{}]
            if provider == "openai":
                for state in ("incomplete", "failed", "cancelled"):
                    body = successful_body(provider)
                    body["status"] = state
                    bodies.append(body)
                body = successful_body(provider)
                body["output"] = []
                bodies.append(body)
            elif provider == "deepseek":
                for reason in ("length", "content_filter", "tool_calls"):
                    body = successful_body(provider)
                    body["choices"][0]["finish_reason"] = reason
                    bodies.append(body)
                for content in (None, "", "  "):
                    body = successful_body(provider)
                    body["choices"][0]["message"]["content"] = content
                    bodies.append(body)
            else:
                for reason in ("max_tokens", "tool_use", "refusal", "pause_turn"):
                    body = successful_body(provider)
                    body["stop_reason"] = reason
                    bodies.append(body)
                body = successful_body(provider)
                body["content"] = [{"type": "thinking", "thinking": "internal"}]
                bodies.append(body)
            for body in bodies:
                with self.subTest(provider=provider, body=body):
                    with self.assertRaises(ai.AIUnavailable):
                        await self.call_provider(provider, body)

    async def test_anthropic_combines_only_text_blocks(self):
        body = successful_body("anthropic")
        body["content"] = [{"type": "thinking", "thinking": "internal"},
                           {"type": "text", "text": "Первая часть"}, {"type": "text", "text": "Вторая часть"}]
        self.assertEqual(await self.call_provider("anthropic", body), "Первая часть\nВторая часть")

    async def test_total_deadline_and_cancellation(self):
        async def slow(*args):
            await asyncio.Event().wait()

        for provider in PROVIDERS:
            with self.subTest(provider=provider), patch.dict(ai._ADAPTERS, {provider: slow}), \
                    patch("services.ai.TIMEOUT_SECONDS", 0.01):
                with self.assertRaisesRegex(ai.AIUnavailable, "timed out"):
                    await ai.generate_ai_response(settings_for(provider), "question", [])
                task = asyncio.create_task(ai.generate_ai_response(settings_for(provider), "question", []))
                await asyncio.sleep(0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task


if __name__ == "__main__":
    unittest.main()
