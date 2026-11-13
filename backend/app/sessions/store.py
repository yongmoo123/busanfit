"""Single-process session store. Never persist or log session contents."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from typing import Callable
from uuid import uuid4
import math


class SessionError(Exception):
    def __init__(self, code: str, status: int, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


@dataclass(repr=False)
class SessionSnapshot:
    session_id: str
    expires_at: datetime
    revision: int = 0
    profile: dict | None = None
    history: list = field(default_factory=list)
    pending_fields: dict[str, str] = field(default_factory=dict)
    companion_hints: dict = field(default_factory=dict)


@dataclass(repr=False)
class _Entry:
    state: SessionSnapshot
    deadline: float
    requests: list[float] = field(default_factory=list)


class SessionStore:
    def __init__(self, *, ttl_seconds: float = 1800, clock: Callable = monotonic,
                 wall_clock: Callable = lambda: datetime.now(timezone.utc),
                 creation_limit: int = 20, max_sessions: int = 1000,
                 max_clients: int = 1000):
        self.ttl_seconds = ttl_seconds
        self._clock, self._wall_clock = clock, wall_clock
        self._creation_limit, self._max_sessions = creation_limit, max_sessions
        self._max_clients = max_clients
        self._entries: dict[str, _Entry] = {}
        self._clients: dict[str, list[float]] = {}
        self._lock = RLock()

    def purge_expired(self):
        with self._lock:
            now = self._clock()
            for key in list(self._entries):
                if self._entries[key].deadline <= now:
                    del self._entries[key]
            for key in list(self._clients):
                recent = [t for t in self._clients[key] if t > now - 60]
                if recent:
                    self._clients[key] = recent
                else:
                    del self._clients[key]

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._clients.clear()

    def _limit(self, requests, now, limit):
        requests[:] = [t for t in requests if t > now - 60]
        if len(requests) >= limit:
            raise SessionError('RATE_LIMITED', 429, max(1, math.ceil(requests[0] + 60 - now)))
        requests.append(now)

    def create(self, client: str) -> SessionSnapshot:
        with self._lock:
            self.purge_expired()
            now = self._clock()
            if len(self._entries) >= self._max_sessions:
                raise SessionError('RATE_LIMITED', 429, 60)
            if client not in self._clients and len(self._clients) >= self._max_clients:
                raise SessionError('RATE_LIMITED', 429, 60)
            self._limit(self._clients.setdefault(client, []), now, self._creation_limit)
            state = SessionSnapshot(str(uuid4()), self._wall_clock() + timedelta(seconds=self.ttl_seconds))
            self._entries[state.session_id] = _Entry(state, now + self.ttl_seconds)
            return deepcopy(state)

    def _entry(self, session_id: str, revision: int) -> _Entry:
        self.purge_expired()
        entry = self._entries.get(session_id)
        if entry is None:
            raise SessionError('SESSION_EXPIRED', 410)
        if entry.state.revision != revision:
            raise SessionError('REVISION_CONFLICT', 409)
        return entry

    def begin(self, session_id: str, expected_revision: int) -> SessionSnapshot:
        """Begin a future chat/profile/course request; failed work does not renew TTL."""
        with self._lock:
            entry = self._entry(session_id, expected_revision)
            self._limit(entry.requests, self._clock(), 20)
            return deepcopy(entry.state)

    def check_current(self, session_id: str, expected_revision: int) -> SessionSnapshot:
        """Recheck slow work without charging a second request or renewing TTL."""
        with self._lock:
            return deepcopy(self._entry(session_id, expected_revision).state)

    def commit_profile(self, session_id: str, expected_revision: int, *, profile: dict, history: list,
                       pending_fields: dict | None = None, companion_hints: dict | None = None) -> SessionSnapshot:
        """Caller validates input first. Atomically commit only a matching revision."""
        profile_copy, history_copy = deepcopy(profile), deepcopy(history)
        pending_copy, hints_copy = deepcopy(pending_fields), deepcopy(companion_hints)
        with self._lock:
            entry = self._entry(session_id, expected_revision)
            entry.state.profile = profile_copy
            entry.state.history = history_copy
            if pending_copy is not None:
                entry.state.pending_fields = pending_copy
            if hints_copy is not None:
                entry.state.companion_hints = hints_copy
            entry.state.revision += 1
            self._renew(entry)
            return deepcopy(entry.state)

    def begin_course(self, session_id: str, expected_revision: int) -> SessionSnapshot:
        """Required entry guard for the future course engine (DEC-021)."""
        with self._lock:
            state = self.begin(session_id, expected_revision)
            if state.pending_fields or state.profile is None or any(
                state.profile[name]['value'] is None for name in ('area', 'timeWindow')
            ):
                raise SessionError('PROFILE_INCOMPLETE', 422)
            return state

    def finish_read(self, session_id: str, expected_revision: int) -> SessionSnapshot:
        """Recheck after course generation; a stale result must not be returned."""
        with self._lock:
            entry = self._entry(session_id, expected_revision)
            self._renew(entry)
            return deepcopy(entry.state)

    def _renew(self, entry):
        entry.deadline = self._clock() + self.ttl_seconds
        entry.state.expires_at = self._wall_clock() + timedelta(seconds=self.ttl_seconds)
