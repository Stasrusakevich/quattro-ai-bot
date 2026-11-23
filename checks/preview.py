"""Collect a private ERP snapshot without Telegram delivery or ERP changes."""

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from config import ROOT
from integrations.erp import ERPClient, ERPError, ERPSettings


async def collect(client, start, end):
    report = {
        "schema_version": 1, "mode": "read_only_preview", "timezone": "Europe/Moscow",
        "from": start, "to_exclusive": end,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "erp_complete": False, "readiness_checked": False,
        "sources": {"erp": "pending", "google_checklists": "not_connected", "telegram_context": "not_connected"},
        "events": [], "unlinked_bookings": [], "issues": [],
    }
    try:
        calendar = await client.calendar(start, end)
    except ERPError as error:
        report["sources"]["erp"] = error.code
        report["issues"].append({"code": error.code, "retry_after": error.retry_after})
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report
    report["calendar"] = calendar
    project_ids = sorted({row["projectId"] for row in calendar["bookings"] if row.get("projectId")})
    report["unlinked_bookings"] = [row for row in calendar["bookings"] if not row.get("projectId")]
    legacy_ids = [row["id"] for row in report["unlinked_bookings"]
                  if row["status"] not in {"blocked", "cancelled"}]
    if legacy_ids:
        report["issues"].append({"code": "event_link_missing", "booking_ids": legacy_ids})
    # Bound the work independently of the amount of data in the requested period.
    if len(project_ids) > 100:
        report["issues"].append({"code": "too_many_events", "count": len(project_ids)})
        report["sources"]["erp"] = "partial"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report
    # Sequential reads avoid adding contention to the ERP's SQLite request queue.
    for project_id in project_ids:
        try:
            report["events"].append(await client.event(project_id))
        except ERPError as error:
            report["issues"].append({"event_id": project_id, "code": error.code})
            if error.code in {"authentication_failed", "rate_limited", "network_unavailable"}:
                break
    try:
        latest = await client.calendar(start, end)
        if latest["viewToken"] != calendar["viewToken"]:
            report["issues"].append({"code": "calendar_changed_during_read"})
    except ERPError as error:
        report["issues"].append({"code": error.code})
    report["erp_complete"] = not report["issues"]
    report["sources"]["erp"] = "ok" if report["erp_complete"] else "partial"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def write_report(report, directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"erp-preview-{stamp}-{uuid4().hex}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return path


async def run(args):
    load_dotenv(ROOT / ".env")
    settings = ERPSettings(
        base_url=os.getenv("ERP_BASE_URL", "https://erp.quattro.space"),
        login_name=os.getenv("ERP_LOGIN_NAME", "Quattro Assistant"),
        username=os.getenv("ERP_USERNAME", ""), password=os.getenv("ERP_PASSWORD", ""),
    )
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else start + timedelta(days=3)
    if not 0 < (end - start).days <= 31:
        raise ValueError("Укажите период от 1 до 31 дня, конечная дата исключается.")
    async with ERPClient(settings) as client:
        report = await collect(client, start.isoformat(), end.isoformat())
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    path = write_report(report, data_dir / "checks")
    print(f"Отчёт сохранён в {path}")
    print(f"ERP: {report['sources']['erp']}. Мероприятий прочитано: {len(report['events'])}.")
    print("Чек-листы и переписка ещё не подключены. Готовность мероприятий не оценивалась.")
    return 0 if report["erp_complete"] else 2


def main():
    # Moscow currently uses UTC+03:00. No scheduling is performed by this command.
    tomorrow = datetime.now(timezone(timedelta(hours=3))).date() + timedelta(days=1)
    parser = argparse.ArgumentParser(description="Пробное чтение ERP без отправки сообщений.")
    parser.add_argument("--from", dest="start", default=tomorrow.isoformat())
    parser.add_argument("--to", dest="end", help="Конечная дата, не включается в период.")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except (ERPError, ValueError, OSError) as error:
        # Do not print arbitrary exception bodies containing connection details or secrets.
        print(f"Проверка не выполнена: {error.code if isinstance(error, ERPError) else type(error).__name__}.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
