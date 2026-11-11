"""SqlitePlaceRepository against the shared PlaceRepository contract, plus SQLite-only checks.

Temporary DB files built from ``schema.sql``. Every row is a [가상] fixture with fixed coordinates;
``insert_records`` is a test helper, not the loader (work C).
"""
import json
import sqlite3
import uuid

import pytest

from app.data import db
from app.data.geo import bounding_box
from app.data.repository import PlaceRepository, RepositoryError
from app.data.sqlite_repository import BOX_SQL, SqlitePlaceRepository
from place_repo_contract import (CENTER, PLACES, RADIUS_M, SOURCES, PlaceRepositoryContract,
                                 pid, place)


def insert_records(conn, places, sources):
    """Write [가상] records the way the loader will: source rows first, then places."""
    for s in sources:
        conn.execute("INSERT INTO data_sources (id, code, provider, dataset_name, license, url, "
                     "base_date, retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (int(s.id), s.code, s.provider, s.dataset_name, s.license, s.url,
                      s.base_date, s.retrieved_at))
    for p in places:
        hours = None if p.open_hours.parsed is None else json.dumps(p.open_hours.parsed)
        row_id = conn.execute(
            "INSERT INTO places (source_place_id, name, category, area, address, latitude, "
            "longitude, indoor, open_hours, open_hours_text, price_amount, price_basis, "
            "price_text, default_stay_min, overview, source_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (p.source_place_id, p.name, p.category, p.area, p.address, p.latitude, p.longitude,
             p.indoor, hours, p.open_hours.text, p.price_amount, p.price_basis, p.price_text,
             p.default_stay_min, p.overview, int(p.source_id), p.updated_at)).lastrowid
        a = p.accessibility
        if a is not None:
            conn.execute("INSERT INTO accessibility (place_id, grade, wheelchair, stroller, "
                         "elevator, accessible_toilet, raw, source_id) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (row_id, a.grade, a.wheelchair, a.stroller, a.elevator,
                          a.accessible_toilet, a.raw, int(a.source_id)))
    conn.commit()


class TestSqlitePlaceRepository(PlaceRepositoryContract):
    @pytest.fixture(autouse=True)
    def _db_dir(self, tmp_path):
        self.tmp_path = tmp_path
        self.connections = []
        yield
        for conn in self.connections:
            conn.close()

    def open_db(self, places=PLACES, sources=SOURCES):
        conn = db.connect(db.create_database(self.tmp_path / f"{uuid.uuid4().hex}.sqlite3"))
        self.connections.append(conn)
        insert_records(conn, places, sources)
        return conn

    def make_repo(self, places, sources):
        return SqlitePlaceRepository(self.open_db(places, sources))

    def make_failing_repo(self):
        conn = self.open_db()
        conn.close()  # closed connection: every call must fail loudly
        return SqlitePlaceRepository(conn)

    # --- SQLite-only ---

    def test_satisfies_protocol_without_db(self):
        assert isinstance(SqlitePlaceRepository(sqlite3.connect(":memory:")), PlaceRepository)

    # Each call against every table it reads (existing_place_ids does not read accessibility).
    @pytest.mark.parametrize("table, call", [
        (table, call)
        for table, calls in {
            "places": ("radius", "get_place", "existing"),
            "data_sources": ("radius", "get_place", "existing"),
            "accessibility": ("radius", "get_place"),
        }.items()
        for call in calls
    ])
    def test_missing_table_raises_repository_error(self, table, call):
        conn = self.open_db()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(f"DROP TABLE {table}")
        repo = SqlitePlaceRepository(conn)
        calls = {"radius": lambda: repo.find_within_radius(*CENTER, RADIUS_M),
                 "get_place": lambda: repo.get_place(pid("10")),
                 "existing": lambda: repo.existing_place_ids([pid("10")])}
        with pytest.raises(RepositoryError):
            calls[call]()

    def test_missing_source_table_breaks_get_sources(self):
        conn = self.open_db()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE data_sources")
        with pytest.raises(RepositoryError):
            SqlitePlaceRepository(conn).get_sources(["1"])

    def test_empty_database_is_empty_list_not_error(self):
        repo = SqlitePlaceRepository(self.open_db([], SOURCES))
        assert repo.find_within_radius(*CENTER, RADIUS_M) == []

    def test_bad_arguments_checked_before_db(self):
        repo = self.make_failing_repo()
        with pytest.raises(ValueError):
            repo.find_within_radius(91, 129.16, 1500)
        with pytest.raises(ValueError):
            repo.find_within_radius(*CENTER, RADIUS_M, area=1)

    def test_box_query_uses_coordinate_index(self):
        conn = self.open_db()
        box = bounding_box(*CENTER, RADIUS_M)
        plan = " ".join(str(row["detail"]) for row in conn.execute(
            f"EXPLAIN QUERY PLAN {BOX_SQL}",
            (box.min_lat, box.max_lat, box.min_lon, box.max_lon)))
        assert "idx_places_lat_lon" in plan, plan

    def test_box_query_with_filters_still_uses_index(self):
        conn = self.open_db()
        box = bounding_box(*CENTER, RADIUS_M)
        sql = BOX_SQL + " AND p.area = ? AND p.category NOT IN (?, ?)"
        plan = " ".join(str(row["detail"]) for row in conn.execute(
            f"EXPLAIN QUERY PLAN {sql}",
            (box.min_lat, box.max_lat, box.min_lon, box.max_lon, "HAEUNDAE", "CAFE", "PARK")))
        assert "idx_places_lat_lon" in plan, plan

    def test_internal_integer_id_not_exposed(self):
        conn = self.open_db()
        internal = conn.execute("SELECT id FROM places WHERE source_place_id = '10'").fetchone()[0]
        repo = SqlitePlaceRepository(conn)
        assert repo.get_place(str(internal)) is None
        assert repo.get_place(pid("10")).id == pid("10")

    @pytest.mark.parametrize("bad_hours", ['{"monday": []}', "{}", "null", "[]"])
    def test_stored_hours_breaking_the_shape_is_storage_error(self, bad_hours):
        conn = self.open_db()
        conn.execute("UPDATE places SET open_hours = ? WHERE source_place_id = '10'", (bad_hours,))
        with pytest.raises(RepositoryError):
            SqlitePlaceRepository(conn).get_place(pid("10"))

    def test_existing_place_ids_in_batches(self):
        many = [place(f"b{i}", 10 + i, "CAFE") for i in range(450)]
        repo = self.make_repo(many, SOURCES)
        asked = [pid(f"b{i}") for i in range(450)] + [pid("nope"), "malformed"]
        assert repo.existing_place_ids(asked) == frozenset(pid(f"b{i}") for i in range(450))

    def test_get_sources_non_numeric_id_is_missing(self):
        repo = self.make_repo(PLACES, SOURCES)
        with pytest.raises(RepositoryError):
            repo.get_sources(["mock-base"])

    def test_connection_row_factory_not_required(self, tmp_path):
        path = db.create_database(tmp_path / "plain.sqlite3")
        writer = db.connect(path)
        insert_records(writer, PLACES, SOURCES)
        writer.close()
        plain = sqlite3.connect(path)  # default tuple rows
        try:
            assert SqlitePlaceRepository(plain).get_place(pid("10")) == PLACES[0]
        finally:
            plain.close()
