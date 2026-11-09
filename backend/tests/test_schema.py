"""schema.sql against SDD 5.2 (DEC-005). Temporary DB files only; rows are [가상]."""
import sqlite3

import pytest

from app.data import db

# (column, type, NOT NULL, PK position) — SDD 5.2 table (DEC-014, DEC-017, DEC-018)
EXPECTED = {
    "data_sources": [
        ("id", "INTEGER", 0, 1), ("provider", "TEXT", 1, 0), ("dataset_name", "TEXT", 1, 0),
        ("license", "TEXT", 0, 0), ("url", "TEXT", 1, 0), ("base_date", "TEXT", 0, 0),
        ("retrieved_at", "TEXT", 1, 0),
    ],
    "places": [
        ("id", "INTEGER", 0, 1), ("source_place_id", "TEXT", 1, 0),
        ("name", "TEXT", 1, 0), ("category", "TEXT", 1, 0), ("area", "TEXT", 1, 0),
        ("address", "TEXT", 0, 0), ("latitude", "REAL", 1, 0), ("longitude", "REAL", 1, 0),
        ("indoor", "INTEGER", 0, 0), ("open_hours", "TEXT", 0, 0),
        ("open_hours_text", "TEXT", 0, 0),
        ("price_amount", "INTEGER", 0, 0), ("price_basis", "TEXT", 0, 0),
        ("price_text", "TEXT", 0, 0), ("default_stay_min", "INTEGER", 1, 0),
        ("overview", "TEXT", 0, 0),
        ("source_id", "INTEGER", 1, 0), ("updated_at", "TEXT", 1, 0),
    ],
    "accessibility": [
        ("place_id", "INTEGER", 0, 1), ("grade", "TEXT", 1, 0), ("wheelchair", "INTEGER", 0, 0),
        ("stroller", "INTEGER", 0, 0), ("elevator", "INTEGER", 0, 0),
        ("accessible_toilet", "INTEGER", 0, 0), ("raw", "TEXT", 0, 0),
        ("source_id", "INTEGER", 1, 0),
    ],
    "stations": [
        ("id", "TEXT", 0, 1), ("name", "TEXT", 1, 0), ("line", "TEXT", 1, 0),
        ("latitude", "REAL", 1, 0), ("longitude", "REAL", 1, 0),
        ("has_elevator", "INTEGER", 1, 0), ("has_locker", "INTEGER", 1, 0),
        ("source_id", "INTEGER", 1, 0),
    ],
    "station_travel": [
        ("from_station", "TEXT", 1, 1), ("to_station", "TEXT", 1, 2),
        ("minutes", "INTEGER", 1, 0), ("transfer", "INTEGER", 1, 0),
    ],
    "facilities": [
        ("id", "INTEGER", 0, 1), ("type", "TEXT", 1, 0), ("name", "TEXT", 0, 0),
        ("latitude", "REAL", 0, 0), ("longitude", "REAL", 0, 0), ("open_hours", "TEXT", 0, 0),
        ("disabled_parking", "INTEGER", 0, 0), ("fee_info", "TEXT", 0, 0),
        ("station_id", "TEXT", 0, 0), ("source_id", "INTEGER", 1, 0),
    ],
    "shared_courses": [
        ("id", "TEXT", 0, 1), ("course_json", "TEXT", 1, 0), ("created_at", "TEXT", 1, 0),
        ("expires_at", "TEXT", 1, 0),
    ],
    "batch_logs": [
        ("id", "INTEGER", 0, 1), ("job", "TEXT", 1, 0), ("started_at", "TEXT", 1, 0),
        ("success_count", "INTEGER", 0, 0), ("fail_count", "INTEGER", 0, 0),
        ("message", "TEXT", 0, 0),
    ],
}

FOREIGN_KEYS = {
    ("places", "source_id", "data_sources", "id"),
    ("accessibility", "place_id", "places", "id"),
    ("accessibility", "source_id", "data_sources", "id"),
    ("stations", "source_id", "data_sources", "id"),
    ("station_travel", "from_station", "stations", "id"),
    ("station_travel", "to_station", "stations", "id"),
    ("facilities", "station_id", "stations", "id"),
    ("facilities", "source_id", "data_sources", "id"),
}

NOW = "2026-11-09T09:00:00+09:00"


@pytest.fixture
def conn(tmp_path):
    path = db.create_database(tmp_path / "test.sqlite3")
    connection = db.connect(path)
    yield connection
    connection.close()


def add_source(conn):
    return conn.execute(
        "INSERT INTO data_sources (provider, dataset_name, url, retrieved_at) VALUES (?, ?, ?, ?)",
        ("[가상] 기관", "[가상] 데이터", "https://example.invalid/busanfit", NOW)).lastrowid


def add_place(conn, source_id=None, **overrides):
    values = dict(source_place_id="mock-1", name="[가상] 장소", category="CAFE", area="HAEUNDAE",
                  latitude=35.16, longitude=129.16, default_stay_min=60, source_id=source_id,
                  updated_at=NOW)
    values.update(overrides)
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    return conn.execute(f"INSERT INTO places ({columns}) VALUES ({marks})",
                        tuple(values.values())).lastrowid


def test_tables_and_columns_match_sdd(conn):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    assert tables == set(EXPECTED)
    for table, columns in EXPECTED.items():
        actual = [(r["name"], r["type"], r["notnull"], r["pk"])
                  for r in conn.execute(f"PRAGMA table_info({table})")]
        assert actual == columns, table


def test_foreign_keys(conn):
    actual = set()
    for table in EXPECTED:
        for row in conn.execute(f"PRAGMA foreign_key_list({table})"):
            actual.add((table, row["from"], row["table"], row["to"]))
    assert actual == FOREIGN_KEYS


def test_schema_version_and_foreign_keys_enabled(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_coordinate_index_used_for_bounding_box(conn):
    plan = " ".join(row["detail"] for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM places "
        "WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?", (35.1, 35.2, 129.1, 129.2)))
    assert "idx_places_lat_lon" in plan


def test_unknown_values_stored_as_null(conn):
    place_id = add_place(conn, add_source(conn))
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    for column in ("address", "indoor", "open_hours", "open_hours_text", "price_amount",
                   "price_basis", "price_text", "overview"):
        assert row[column] is None, column
    conn.execute("INSERT INTO accessibility (place_id, grade, source_id) VALUES (?, 'UNKNOWN', ?)",
                 (place_id, row["source_id"]))
    access = conn.execute("SELECT * FROM accessibility").fetchone()
    assert [access[c] for c in ("wheelchair", "stroller", "elevator", "accessible_toilet")] \
        == [None] * 4


@pytest.mark.parametrize("category", [
    "CAFE", "FOOD", "EXHIBITION", "ATTRACTION", "PARK", "SHOPPING", "OTHER",
])
def test_contract_categories_accepted(conn, category):
    add_place(conn, add_source(conn), category=category)


@pytest.mark.parametrize("basis", ["PER_PERSON", "TOTAL"])
def test_price_fields_stored(conn, basis):
    place_id = add_place(conn, add_source(conn), price_amount=5000, price_basis=basis,
                         price_text="[가상] 5,000원")
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    assert (row["price_amount"], row["price_basis"], row["price_text"]) \
        == (5000, basis, "[가상] 5,000원")


@pytest.mark.parametrize("overrides", [
    {"indoor": 2}, {"category": "[가상] 체험"}, {"category": "cafe"}, {"category": None},
    {"price_basis": "UNKNOWN"}, {"source_place_id": None}, {"default_stay_min": 0},
    {"latitude": 91}, {"longitude": -181}, {"open_hours": "not json"}, {"name": None},
    {"latitude": None}, {"source_id": 999},
    {"default_stay_min": 1.5}, {"default_stay_min": "unknown"},
    {"price_amount": 1.5}, {"price_amount": "unknown"},
])
def test_invalid_place_rejected(conn, overrides):
    values = {"source_id": add_source(conn), **overrides}
    with pytest.raises(sqlite3.IntegrityError):
        add_place(conn, **values)


def add_station(conn, station_id, source_id):
    conn.execute("INSERT INTO stations (id, name, line, latitude, longitude, has_elevator, "
                 "has_locker, source_id) VALUES (?, '[가상] 역', '[가상] 호선', 35.16, 129.16, 0, 0, ?)",
                 (station_id, source_id))


TRAVEL_SQL = "INSERT INTO station_travel (from_station, to_station, minutes, transfer) " \
             "VALUES ('A', 'B', ?, 0)"


def test_station_travel_minutes_accepts_integer(conn):
    source_id = add_source(conn)
    add_station(conn, "A", source_id)
    add_station(conn, "B", source_id)
    conn.execute(TRAVEL_SQL, (5,))
    row = conn.execute("SELECT minutes, typeof(minutes) AS kind FROM station_travel").fetchone()
    assert (row["minutes"], row["kind"]) == (5, "integer")


@pytest.mark.parametrize("minutes", [1.5, "unknown", -1])
def test_station_travel_minutes_must_be_integer(conn, minutes):
    source_id = add_source(conn)
    add_station(conn, "A", source_id)
    add_station(conn, "B", source_id)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(TRAVEL_SQL, (minutes,))


BATCH_SQL = "INSERT INTO batch_logs (job, started_at, success_count, fail_count) " \
            "VALUES ('[가상]', 'x', ?, ?)"


def test_batch_log_counts_accept_null_and_integer(conn):
    conn.execute(BATCH_SQL, (None, None))
    conn.execute(BATCH_SQL, (3, 0))


@pytest.mark.parametrize("counts", [(1.5, 0), ("unknown", 0), (0, 1.5), (0, "unknown")])
def test_batch_log_counts_must_be_integer(conn, counts):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(BATCH_SQL, counts)


def test_duplicate_source_place_id_rejected(conn):
    source_id = add_source(conn)
    add_place(conn, source_id)
    with pytest.raises(sqlite3.IntegrityError):
        add_place(conn, source_id)
    add_place(conn, add_source(conn))  # same original ID from another source is allowed


@pytest.mark.parametrize("sql", [
    "INSERT INTO accessibility (place_id, grade, source_id) VALUES (:p, 'GOOD', :s)",
    "INSERT INTO accessibility (place_id, grade, wheelchair, source_id) VALUES (:p, 'VERIFIED', 2, :s)",
    "INSERT INTO accessibility (place_id, grade, source_id) VALUES (999, 'UNKNOWN', :s)",
    "INSERT INTO accessibility (place_id, grade, source_id) VALUES (:p, 'UNKNOWN', 999)",
    "INSERT INTO data_sources (provider, dataset_name, url) "
    "VALUES ('[가상]', '[가상]', 'https://example.invalid')",
    "INSERT INTO data_sources (provider, dataset_name, retrieved_at) VALUES ('[가상]', '[가상]', 'x')",
    "INSERT INTO data_sources (provider, dataset_name, url, retrieved_at) "
    "VALUES ('[가상]', '[가상]', NULL, 'x')",
])
def test_invalid_accessibility_and_source_rejected(conn, sql):
    source_id = add_source(conn)
    params = {"p": add_place(conn, source_id), "s": source_id}
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, params)


def test_db_path_comes_from_environment(tmp_path):
    with pytest.raises(db.DatabaseConfigError):
        db.get_db_path({})
    with pytest.raises(db.DatabaseConfigError):
        db.get_db_path({db.ENV_DB_PATH: "  "})
    assert db.get_db_path({db.ENV_DB_PATH: str(tmp_path / "x.sqlite3")}) == tmp_path / "x.sqlite3"


def test_connect_does_not_create_missing_file(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        db.connect(tmp_path / "missing.sqlite3")
    assert not (tmp_path / "missing.sqlite3").exists()


def test_create_database_refuses_existing_file(tmp_path):
    path = db.create_database(tmp_path / "a.sqlite3")
    with pytest.raises(FileExistsError):
        db.create_database(path)


def test_cli_create_uses_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(db.ENV_DB_PATH, raising=False)
    assert db.main(["create"]) == 1
    monkeypatch.setenv(db.ENV_DB_PATH, str(tmp_path / "cli.sqlite3"))
    assert db.main(["create"]) == 0
    assert (tmp_path / "cli.sqlite3").exists()
    assert db.main(["create"]) == 1
    assert db.main([]) == 2
