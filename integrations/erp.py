"""Read the existing ERP APIs with a short-lived password session."""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import time
from urllib.parse import quote, urljoin, urlsplit

import httpx


class ERPError(Exception):
    """A public error code, without source bodies, credentials or cookie values."""

    def __init__(self, code, retry_after=None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


@dataclass(frozen=True)
class ERPSettings:
    base_url: str = "https://erp.quattro.space"
    login_name: str = "Quattro Assistant"
    username: str = ""
    password: str = field(default="", repr=False)

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("ERP_BASE_URL должен быть HTTPS-адресом без пути и параметров.")
        if not self.password:
            raise ValueError("Задайте ERP_PASSWORD в серверных секретах.")


class LoginInputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.names.add(dict(attrs).get("name"))


def revision(value):
    return type(value) is int and value >= 0


def validate_bookings(body):
    if not isinstance(body, dict) or not revision(body.get("revision")):
        raise ERPError("invalid_calendar_response")
    rows = body.get("bookings")
    if not isinstance(rows, list):
        raise ERPError("invalid_calendar_response")
    ids = set()
    statuses = {"inquiry", "option", "tentative", "confirmed", "blocked", "cancelled"}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row["id"] or row["id"] in ids or row.get("status") not in statuses
                or not isinstance(row.get("hall"), str) or not row["hall"]
                or not isinstance(row.get("date"), str)):
            raise ERPError("invalid_calendar_response")
        try:
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError
        except ValueError:
            raise ERPError("invalid_calendar_response") from None
        if row.get("projectId") is not None and not isinstance(row["projectId"], str):
            raise ERPError("invalid_calendar_response")
        ids.add(row["id"])
    return body


class ERPClient:
    def __init__(self, settings, *, transport=None, sleep=asyncio.sleep):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/"), transport=transport,
            follow_redirects=False, timeout=20, trust_env=False,
            headers={"Accept": "application/json", "Cache-Control": "no-cache"},
        )
        self.sleep = sleep
        self.auth_lock = asyncio.Lock()
        self.auth_generation = 0
        self.auth_failed = False
        self.blocked_until = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _request(self, method, path, **kwargs):
        if time.monotonic() < self.blocked_until:
            raise ERPError("rate_limited", self.blocked_until - time.monotonic())
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                # Stream to bound memory even if the server sends no Content-Length.
                async with self.client.stream(method, path, **kwargs) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 20 * 1024 * 1024:
                            raise ERPError("response_too_large")
                    response = httpx.Response(
                        response.status_code, headers=response.headers,
                        content=bytes(content), request=response.request,
                    )
            except httpx.TransportError:
                if attempt + 1 == attempts:
                    raise ERPError("network_unavailable") from None
                await self.sleep(1)
                continue
            if response.status_code == 429:
                # HTTP Retry-After can be a delay or a full HTTP date.
                raw = response.headers.get("Retry-After", "60")
                try:
                    delay = max(1, float(raw))
                    if not 0 < delay < float("inf"):
                        raise ValueError
                except ValueError:
                    from email.utils import parsedate_to_datetime
                    try:
                        delay = max(1, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        delay = 60
                self.blocked_until = time.monotonic() + delay
                raise ERPError("rate_limited", delay)
            if response.status_code in (502, 503, 504) and attempt + 1 < attempts:
                await self.sleep(1)
                continue
            return response
        raise ERPError("network_unavailable")

    async def _login(self, observed_generation):
        async with self.auth_lock:
            if self.auth_failed:
                raise ERPError("authentication_failed")
            if self.auth_generation != observed_generation:
                return
            form = await self._request("GET", "/auth/login")
            if form.status_code != 200:
                raise ERPError("login_unavailable")
            inputs = LoginInputs()
            inputs.feed(form.text)
            if "password" not in inputs.names:
                raise ERPError("unsupported_login_form")
            data = {"password": self.settings.password}
            if "username" in inputs.names:
                if not self.settings.username:
                    raise ERPError("username_required")
                data["username"] = self.settings.username
            elif "name" in inputs.names:
                data["name"] = self.settings.login_name
            else:
                raise ERPError("unsupported_login_form")
            self.client.cookies.clear()
            response = await self._request("POST", "/auth/login", data=data)
            if response.status_code in (400, 401, 403):
                self.auth_failed = True
                raise ERPError("authentication_failed")
            location = urljoin(self.settings.base_url, response.headers.get("Location", ""))
            if (response.status_code != 303
                    or urlsplit(location).netloc != urlsplit(self.settings.base_url).netloc
                    or urlsplit(location).scheme != "https"
                    or not any(cookie.name == "__Host-qs-session" for cookie in self.client.cookies.jar)):
                raise ERPError("invalid_login_response")
            self.auth_generation += 1

    async def _get_json(self, path, **params):
        generation = self.auth_generation
        if generation == 0:
            await self._login(generation)
        generation = self.auth_generation
        response = await self._request("GET", path, params=params)
        if response.status_code == 401:
            await self._login(generation)
            response = await self._request("GET", path, params=params)
        if response.status_code == 401:
            self.auth_failed = True
            raise ERPError("authentication_failed")
        if response.status_code != 200:
            raise ERPError(f"http_{response.status_code}")
        if "application/json" not in response.headers.get("Content-Type", "").lower():
            raise ERPError("invalid_json_response")
        try:
            body = response.json()
        except ValueError:
            raise ERPError("invalid_json_response") from None
        if not isinstance(body, dict):
            raise ERPError("invalid_json_response")
        return body

    async def calendar(self, start, end):
        if not 0 < (date.fromisoformat(end) - date.fromisoformat(start)).days <= 31:
            raise ValueError("Период чтения должен составлять от 1 до 31 дня, конец исключается.")
        body = validate_bookings(await self._get_json("/api/calendar/view", **{"from": start, "to": end}))
        if (body.get("scope") != {"kind": "view", "from": start, "to": end}
                or body.get("from") != start or body.get("to") != end
                or not isinstance(body.get("viewToken"), str) or not body["viewToken"]):
            raise ERPError("invalid_calendar_scope")
        return body

    async def reservations(self, project_id):
        body = validate_bookings(await self._get_json(self._project_path(project_id) + "/reservations"))
        if (body.get("scope") != {"kind": "project", "projectId": project_id}
                or any(row.get("projectId") != project_id for row in body["bookings"])):
            raise ERPError("invalid_project_scope")
        return body

    def _project_path(self, project_id):
        if not isinstance(project_id, str) or not project_id or len(project_id) > 200 or project_id in {".", ".."}:
            raise ValueError("Некорректный ID мероприятия.")
        return "/api/projects/" + quote(project_id, safe="")

    async def event(self, project_id):
        # Read group → card → group to detect a concurrent calendar or estimate edit.
        for attempt in range(2):
            before = await self.reservations(project_id)
            card = await self._get_json(self._project_path(project_id))
            project = card.get("project")
            if project is None:
                raise ERPError("project_missing")
            if (not revision(card.get("revision")) or not isinstance(project, dict)
                    or project.get("projectId") != project_id
                    or not isinstance(project.get("event"), dict)
                    or not isinstance(project.get("estimate"), dict)):
                raise ERPError("invalid_project_response")
            after = await self.reservations(project_id)
            if any(not isinstance(body.get(key), dict) for body in (before, after)
                   for key in ("reservationGroupRevisions", "projectRevisions")):
                raise ERPError("version_contract_missing")
            group_versions = [body["reservationGroupRevisions"].get(project_id)
                              for body in (before, after)]
            card_versions = [body["projectRevisions"].get(project_id)
                             for body in (before, after)]
            if not all(revision(value) for value in group_versions + card_versions):
                raise ERPError("version_contract_missing")
            if group_versions[0] == group_versions[1] and card_versions == [card["revision"]] * 2:
                return {
                    "event_id": project_id,
                    "url": self.settings.base_url.rstrip("/") + "/events/" + quote(project_id, safe="") + "/estimate",
                    "read_at": datetime.now(timezone.utc).isoformat(),
                    "project_revision": card["revision"],
                    "reservation_group_revision": group_versions[1],
                    "project": project, "bookings": after["bookings"],
                }
            if attempt == 0:
                await self.sleep(0)
        raise ERPError("event_changed_during_read")
