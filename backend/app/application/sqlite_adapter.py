"""Connect the existing PR #41 Repository to API worker threads safely.

One connection per call; never share a default SQLite connection across threads.
No SQL, retrieval policy, travel formula, database creation or automatic activation.
"""
from pathlib import Path
import sqlite3

from app.data.db import connect
from app.data.repository import RepositoryError, check_categories, check_id, check_id_list, check_radius_query
from app.data.sqlite_repository import SqlitePlaceRepository


class ConnectionPerCallRepository:
    def __init__(self, path: str | Path, *, read_only: bool = False):
        self.path = Path(path).resolve()
        self.read_only = read_only

    def _call(self, name, *args, **kwargs):
        try:
            connection = connect(self.path, read_only=True) if self.read_only else connect(self.path)
        except sqlite3.Error:
            raise RepositoryError('SQLite connection unavailable') from None
        try:
            return getattr(SqlitePlaceRepository(connection), name)(*args, **kwargs)
        finally:
            connection.close()

    def get_place(self, place_id):
        check_id(place_id)
        return self._call('get_place', place_id)

    def get_sources(self, source_ids):
        return self._call('get_sources', check_id_list(source_ids, 'source_ids'))

    def existing_place_ids(self, place_ids):
        return self._call('existing_place_ids', check_id_list(place_ids))

    def find_within_radius(self, center_lat, center_lon, radius_m, *, area=None, exclude_categories=(), limit=None):
        check_radius_query(center_lat, center_lon, radius_m, limit)
        excluded = check_categories(exclude_categories)
        if area is not None and not isinstance(area, str):
            raise ValueError('area must be a string or None')
        return self._call('find_within_radius', center_lat, center_lon, radius_m,
                          area=area, exclude_categories=excluded, limit=limit)
