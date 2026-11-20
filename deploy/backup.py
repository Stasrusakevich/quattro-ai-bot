"""Create a consistent SQLite backup without exposing table contents."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


def backup_database(source: Path, destination: Path) -> Path:
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Source must be a SQLite file")

    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = destination.resolve(strict=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = destination / f"{source.stem}-{timestamp}-{uuid.uuid4().hex[:8]}.sqlite"
    with target.open("xb"):
        pass
    target.chmod(0o600)

    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            with closing(sqlite3.connect(target)) as copy:
                origin.backup(copy, pages=256, sleep=0.1)
                result = copy.execute("PRAGMA integrity_check").fetchone()
                if result != ("ok",):
                    raise RuntimeError("Backup integrity check failed")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    target = backup_database(arguments.source, arguments.destination)
    print(target)


if __name__ == "__main__":
    main()
