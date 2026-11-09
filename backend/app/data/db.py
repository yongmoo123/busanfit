"""SQLite file location and schema creation (DEC-005, SDD 5.2).

The DB path comes only from the environment variable ``BUSANFIT_DB_PATH``. No default path:
a missing setting must fail loudly instead of silently opening an empty database.

    cd backend
    python -m app.data.db create      # new empty DB at $BUSANFIT_DB_PATH (refuses to overwrite)
"""
from collections.abc import Mapping
import os
from pathlib import Path
import sqlite3
import sys

ENV_DB_PATH = "BUSANFIT_DB_PATH"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabaseConfigError(RuntimeError):
    """The DB location is not configured."""


def get_db_path(environ: Mapping[str, str] | None = None) -> Path:
    value = (os.environ if environ is None else environ).get(ENV_DB_PATH, "").strip()
    if not value:
        raise DatabaseConfigError(f"{ENV_DB_PATH} is not set")
    return Path(value)


def connect(path: str | Path | None = None, *, create: bool = False) -> sqlite3.Connection:
    """Open the DB with foreign keys on. Without ``create``, a missing file is an error."""
    db_path = Path(path) if path is not None else get_db_path()
    mode = "rwc" if create else "rw"
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def create_database(path: str | Path | None = None) -> Path:
    """Create a new DB file with the schema. Refuses to touch an existing file."""
    db_path = Path(path) if path is not None else get_db_path()
    if db_path.exists():
        raise FileExistsError(f"{db_path} already exists; remove it explicitly to rebuild")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path, create=True)
    try:
        create_schema(conn)
    finally:
        conn.close()
    return db_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["create"]:
        print("usage: python -m app.data.db create", file=sys.stderr)
        return 2
    try:
        created = create_database()
    except (DatabaseConfigError, FileExistsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"created {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
