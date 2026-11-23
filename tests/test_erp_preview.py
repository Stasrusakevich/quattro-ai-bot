import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from checks.preview import collect, run, write_report
from integrations.erp import ERPClient, ERPError, ERPSettings


def booking(booking_id="b1", project_id="e1", hall="Шале", day="2026-11-24", status="confirmed"):
    return {
        "id": booking_id, "projectId": project_id, "hall": hall, "date": day,
        "status": status, "start": "18:00", "end": "23:00",
        "setupStart": "2026-11-24T12:00", "teardownEnd": "2026-11-25T02:00",
    }


class ERPFixture:
    def __init__(self):
        self.calls = []
        self.logins = 0
        self.mode = "shared"
        self.login_status = 303
        self.expire_once = False
        self.reject_session = False
        self.edit_once = False
        self.keep_editing = False
        self.version = 1
        self.token = "view-1"
        self.rows = [booking(), booking("b2", hall="Гримёрная"),
                     booking("b3", day="2026-11-25", status="option")]

    def group(self):
        return {
            "revision": 10, "scope": {"kind": "project", "projectId": "e1"},
            "bookings": deepcopy([row for row in self.rows if row.get("projectId") == "e1"]),
            "projectRevisions": {"e1": self.version},
            "reservationGroupRevisions": {"e1": self.version},
        }

    def calendar(self):
        return {
            "revision": 10, "from": "2026-11-24", "to": "2026-11-27",
            "viewToken": self.token,
            "scope": {"kind": "view", "from": "2026-11-24", "to": "2026-11-27"},
            "bookings": deepcopy(self.rows),
        }

    def handle(self, request):
        self.calls.append(request)
        path = request.url.path
        if path == "/auth/login":
            if request.method == "GET":
                name = "username" if self.mode == "personal" else "name"
                return httpx.Response(200, text=f'<input name="{name}"><input name="password">')
            self.logins += 1
            headers = {"Location": "/", "Set-Cookie": f"__Host-qs-session=session{self.logins}; Path=/; Secure; HttpOnly"}
            return httpx.Response(self.login_status, headers=headers)
        if self.reject_session or self.expire_once:
            self.expire_once = False
            return httpx.Response(401, json={"error": "expired"})
        if path == "/api/calendar/view":
            return httpx.Response(200, json=self.calendar())
        if path == "/api/projects/e1/reservations":
            return httpx.Response(200, json=self.group())
        if path == "/api/projects/e1":
            body = {
                "revision": self.version,
                "project": {"projectId": "e1", "event": {"responsible": "Ольга"},
                            "estimate": {"status": "approved", "revision": self.version,
                                         "summary": [{"title": "Персонал", "lines": [
                                             {"name": "Официант", "quantity": 2, "unit": "чел", "sum": 14000},
                                         ]}]}},
            }
            if self.edit_once or self.keep_editing:
                self.version += 1
                self.edit_once = False
            return httpx.Response(200, json=body)
        raise AssertionError(f"Unexpected ERP route {request.method} {path}")


class ERPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = ERPFixture()
        self.sleep = AsyncMock()
        self.client = ERPClient(
            ERPSettings(base_url="https://erp.example", password="private-password"),
            transport=httpx.MockTransport(self.fixture.handle), sleep=self.sleep,
        )
        self.addAsyncCleanup(self.client.client.aclose)

    async def test_shared_login_cookie_and_full_estimate_are_read(self):
        body = await self.client.event("e1")
        self.assertEqual(body["project"]["estimate"]["summary"][0]["lines"][0]["quantity"], 2)
        self.assertEqual(body["project_revision"], 1)
        self.assertEqual(body["url"], "https://erp.example/events/e1/estimate")
        self.assertEqual(len(body["bookings"]), 3)
        self.assertEqual(self.fixture.logins, 1)
        self.assertIn("__Host-qs-session=session1", self.fixture.calls[2].headers["Cookie"])
        self.assertTrue(all(r.method == "GET" or r.url.path == "/auth/login" for r in self.fixture.calls))

    async def test_concurrent_reads_login_once(self):
        await asyncio.gather(*(self.client.calendar("2026-11-24", "2026-11-27") for _ in range(5)))
        self.assertEqual(self.fixture.logins, 1)

    async def test_personal_login_requires_existing_username(self):
        self.fixture.mode = "personal"
        with self.assertRaisesRegex(ERPError, "username_required"):
            await self.client.event("e1")
        self.assertEqual(self.fixture.logins, 0)

    async def test_personal_login_uses_username(self):
        self.fixture.mode = "personal"
        self.client.settings = ERPSettings(base_url="https://erp.example", username="existing", password="secret")
        await self.client.event("e1")
        self.assertIn(b"username=existing", self.fixture.calls[1].content)
        self.assertNotIn(b"name=Quattro", self.fixture.calls[1].content)

    async def test_expired_session_reauthenticates_once(self):
        await self.client.event("e1")
        self.fixture.expire_once = True
        await self.client.event("e1")
        self.assertEqual(self.fixture.logins, 2)

    async def test_invalid_password_is_not_retried(self):
        self.fixture.login_status = 401
        for _ in range(2):
            with self.assertRaisesRegex(ERPError, "authentication_failed"):
                await self.client.event("e1")
        self.assertEqual(self.fixture.logins, 1)

    async def test_session_rejection_does_not_loop(self):
        self.fixture.reject_session = True
        with self.assertRaisesRegex(ERPError, "authentication_failed"):
            await self.client.event("e1")
        self.assertEqual(self.fixture.logins, 2)

    async def test_rate_limit_respects_cooldown_without_reposting_login(self):
        self.client.client._transport = httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "70"}))
        for _ in range(2):
            with self.assertRaises(ERPError) as error:
                await self.client.event("e1")
            self.assertEqual(error.exception.code, "rate_limited")
            self.assertGreater(error.exception.retry_after, 60)
        self.sleep.assert_not_awaited()

    async def test_network_retries_are_bounded_and_hide_credentials(self):
        calls = []
        def fail(request):
            calls.append(request)
            raise httpx.ConnectError("private-password", request=request)
        self.client.client._transport = httpx.MockTransport(fail)
        with self.assertRaises(ERPError) as error:
            await self.client.event("e1")
        self.assertEqual(str(error.exception), "network_unavailable")
        self.assertIsNone(error.exception.__cause__)
        self.assertEqual(len(calls), 2)

    async def test_get_transient_error_is_retried_once(self):
        calls = 0
        def handle(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503)
            return self.fixture.handle(request)
        self.client.client._transport = httpx.MockTransport(handle)
        await self.client.event("e1")
        self.sleep.assert_awaited_once_with(1)

    async def test_login_transport_failure_is_not_reposted(self):
        calls = []
        def handle(request):
            calls.append(request)
            if request.method == "POST":
                raise httpx.ReadTimeout("secret", request=request)
            return self.fixture.handle(request)
        self.client.client._transport = httpx.MockTransport(handle)
        with self.assertRaisesRegex(ERPError, "network_unavailable"):
            await self.client.event("e1")
        self.assertEqual(sum(r.method == "POST" for r in calls), 1)

    async def test_redirect_is_not_followed(self):
        self.client.client._transport = httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"Location": "https://other.example"}))
        with self.assertRaisesRegex(ERPError, "login_unavailable"):
            await self.client.event("e1")

    async def test_cross_origin_login_result_is_rejected(self):
        def handle(request):
            response = self.fixture.handle(request)
            if request.method == "POST":
                response.headers["Location"] = "https://other.example"
            return response
        self.client.client._transport = httpx.MockTransport(handle)
        with self.assertRaisesRegex(ERPError, "invalid_login_response"):
            await self.client.event("e1")

    async def test_foreign_reservation_is_rejected(self):
        original = self.fixture.group
        def group():
            body = original()
            body["bookings"][0]["projectId"] = "foreign"
            return body
        self.fixture.group = group
        with self.assertRaisesRegex(ERPError, "invalid_project_scope"):
            await self.client.event("e1")

    async def test_missing_version_contract_is_explicit(self):
        original = self.fixture.group
        def group():
            body = original()
            del body["reservationGroupRevisions"]
            return body
        self.fixture.group = group
        with self.assertRaisesRegex(ERPError, "version_contract_missing"):
            await self.client.event("e1")

    async def test_concurrent_event_edit_reads_fresh_consistent_version(self):
        self.fixture.edit_once = True
        body = await self.client.event("e1")
        self.assertEqual(body["project_revision"], 2)
        self.assertEqual(body["reservation_group_revision"], 2)

    async def test_continuously_changing_event_is_incomplete(self):
        self.fixture.keep_editing = True
        with self.assertRaisesRegex(ERPError, "event_changed_during_read"):
            await self.client.event("e1")

    async def test_wrong_scope_does_not_become_empty_calendar(self):
        original = self.fixture.calendar
        def calendar():
            body = original()
            body["scope"]["to"] = "2026-12-01"
            return body
        self.fixture.calendar = calendar
        with self.assertRaisesRegex(ERPError, "invalid_calendar_scope"):
            await self.client.calendar("2026-11-24", "2026-11-27")

    async def test_duplicate_or_unknown_status_bookings_are_rejected(self):
        self.fixture.rows.append(booking())
        with self.assertRaisesRegex(ERPError, "invalid_calendar_response"):
            await self.client.calendar("2026-11-24", "2026-11-27")
        self.fixture.rows.pop()
        self.fixture.rows[0]["status"] = "new_unsupported_status"
        with self.assertRaisesRegex(ERPError, "invalid_calendar_response"):
            await self.client.calendar("2026-11-24", "2026-11-27")

    async def test_html_error_is_not_json_and_does_not_expose_body(self):
        def handle(request):
            if request.url.path.startswith("/api/"):
                return httpx.Response(200, text="secret internal response", headers={"Content-Type": "text/html"})
            return self.fixture.handle(request)
        self.client.client._transport = httpx.MockTransport(handle)
        with self.assertRaisesRegex(ERPError, "invalid_json_response"):
            await self.client.calendar("2026-11-24", "2026-11-27")

    async def test_collection_keeps_all_statuses_halls_dates_and_one_event(self):
        self.fixture.rows.extend([booking("cancelled", status="cancelled"),
                                  booking("inquiry", status="inquiry"),
                                  booking("tentative", status="tentative"),
                                  booking("technical", project_id=None, status="blocked")])
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertTrue(report["erp_complete"])
        self.assertEqual(len(report["events"]), 1)
        self.assertEqual(len(report["events"][0]["bookings"]), 6)
        self.assertEqual(len(report["unlinked_bookings"]), 1)
        self.assertFalse(report["readiness_checked"])
        self.assertEqual(report["sources"]["google_checklists"], "not_connected")
        self.assertEqual(report["calendar"]["bookings"][0]["teardownEnd"], "2026-11-25T02:00")

    async def test_legacy_booking_without_event_is_kept_for_review(self):
        self.fixture.rows.append(booking("old", project_id=None))
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertFalse(report["erp_complete"])
        self.assertEqual(report["unlinked_bookings"][0]["id"], "old")
        self.assertIn({"code": "event_link_missing", "booking_ids": ["old"]}, report["issues"])

    async def test_missing_card_keeps_other_verified_source_data(self):
        original = self.fixture.handle
        def handle(request):
            if request.url.path == "/api/projects/e1":
                return httpx.Response(200, json={"project": None, "revision": 0})
            return original(request)
        self.client.client._transport = httpx.MockTransport(handle)
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertFalse(report["erp_complete"])
        self.assertEqual(len(report["calendar"]["bookings"]), 3)
        self.assertIn({"event_id": "e1", "code": "project_missing"}, report["issues"])

    async def test_response_size_is_bounded(self):
        self.client.client._transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (20 * 1024 * 1024 + 1)))
        with self.assertRaisesRegex(ERPError, "response_too_large"):
            await self.client.event("e1")

    async def test_versions_with_wrong_type_are_rejected(self):
        original = self.fixture.group
        def group():
            body = original()
            body["reservationGroupRevisions"] = []
            return body
        self.fixture.group = group
        with self.assertRaisesRegex(ERPError, "version_contract_missing"):
            await self.client.event("e1")

    async def test_event_limit_does_not_read_unbounded_cards(self):
        self.fixture.rows = [booking(f"b{i}", f"e{i}") for i in range(101)]
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertFalse(report["erp_complete"])
        self.assertEqual(report["events"], [])
        self.assertIn({"code": "too_many_events", "count": 101}, report["issues"])
        self.assertFalse(any("/api/projects/" in str(r.url) for r in self.fixture.calls))

    async def test_cli_entry_point_writes_private_report_without_telegram_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with (patch.dict("os.environ", {"ERP_PASSWORD": "private-password", "DATA_DIR": directory}, clear=True),
                  patch("checks.preview.load_dotenv"),
                  patch("checks.preview.ERPClient", return_value=self.client),
                  patch("sys.stdout", output)):
                result = await run(SimpleNamespace(start="2026-11-24", end="2026-11-27"))
            self.assertEqual(result, 0)
            path, = (Path(directory) / "checks").glob("*.json")
            report_text = path.read_text(encoding="utf-8")
            self.assertTrue(json.loads(report_text)["erp_complete"])
            self.assertNotIn("private-password", report_text + output.getvalue())
            self.assertNotIn("__Host-qs-session", report_text + output.getvalue())
            self.assertIn("не оценивалась", output.getvalue())

    async def test_calendar_change_during_collection_is_partial(self):
        original = self.fixture.handle
        def handle(request):
            if request.url.path == "/api/projects/e1":
                self.fixture.token = "changed"
            return original(request)
        self.client.client._transport = httpx.MockTransport(handle)
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertFalse(report["erp_complete"])
        self.assertIn({"code": "calendar_changed_during_read"}, report["issues"])

    async def test_failed_erp_is_not_treated_as_no_events(self):
        self.fixture.login_status = 401
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertFalse(report["erp_complete"])
        self.assertEqual(report["sources"]["erp"], "authentication_failed")
        self.assertFalse(report["readiness_checked"])

    async def test_empty_calendar_is_complete_erp_only(self):
        self.fixture.rows = []
        report = await collect(self.client, "2026-11-24", "2026-11-27")
        self.assertTrue(report["erp_complete"])
        self.assertEqual(report["events"], [])
        self.assertFalse(report["readiness_checked"])

    async def test_calendar_request_is_bounded(self):
        for start, end in [("2026-11-24", "2026-11-24"), ("2026-11-24", "2027-01-01")]:
            with self.assertRaises(ValueError):
                await self.client.calendar(start, end)
        self.assertEqual(self.fixture.calls, [])


class ConfigurationAndReportTests(unittest.TestCase):
    def test_password_not_in_settings_repr(self):
        self.assertNotIn("private-password", repr(ERPSettings(password="private-password")))

    def test_only_https_origins_are_accepted(self):
        for url in ["http://erp.example", "https://u:p@erp.example", "https://erp.example/api",
                    "https://erp.example?secret=x", "https://erp.example/#x"]:
            with self.assertRaises(ValueError):
                ERPSettings(base_url=url, password="p")

    def test_private_report_roundtrip_and_distinct_files(self):
        with tempfile.TemporaryDirectory() as directory:
            report = {"erp_complete": False, "events": [{"title": "Шале"}]}
            with patch("checks.preview.datetime") as clock:
                clock.now.return_value = datetime(2026, 11, 23, tzinfo=timezone.utc)
                first = write_report(report, Path(directory) / "checks")
                second = write_report(report, Path(directory) / "checks")
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()
