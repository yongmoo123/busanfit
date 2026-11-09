-- 부산핏 SQLite 스키마 — SDD 5.2 / 그림 5-1 (DEC-005)
-- 타입은 SQLite 실제 타입만 사용: 불리언 INTEGER 0/1, 시각 TEXT ISO 8601, JSON TEXT, UUID TEXT.
-- 새 DB 파일에 한 번 적용한다(CREATE TABLE, IF NOT EXISTS 없음). 갱신은 새 파일을 만든 뒤 교체한다.
-- 이슈 #7 미확정 가정으로 추가한 컬럼: places.source_place_id / overview / open_hours_text,
-- data_sources.retrieved_at. places.category는 값 제한 없음(정할 것 2 대기).
-- 외래 키는 연결마다 PRAGMA foreign_keys = ON 이 필요하다(app.data.db.connect가 설정).

PRAGMA user_version = 1;

CREATE TABLE data_sources (
    id            INTEGER PRIMARY KEY,
    provider      TEXT NOT NULL,
    dataset_name  TEXT NOT NULL,
    license       TEXT,
    url           TEXT,
    base_date     TEXT,
    retrieved_at  TEXT NOT NULL
);

CREATE TABLE places (
    id                INTEGER PRIMARY KEY,
    source_place_id   TEXT,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    area              TEXT NOT NULL,
    address           TEXT,
    latitude          REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude         REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    indoor            INTEGER CHECK (indoor IN (0, 1)),
    open_hours        TEXT CHECK (open_hours IS NULL OR json_valid(open_hours)),
    open_hours_text   TEXT,
    price_level       INTEGER CHECK (price_level BETWEEN 1 AND 4),
    default_stay_min  INTEGER NOT NULL CHECK (default_stay_min > 0),
    overview          TEXT,
    source_id         INTEGER NOT NULL REFERENCES data_sources (id),
    updated_at        TEXT NOT NULL,
    UNIQUE (source_id, source_place_id)
);

-- 반경 검색의 위경도 사각형 1차 필터용 (2차는 파이썬 하버사인)
CREATE INDEX idx_places_lat_lon ON places (latitude, longitude);

CREATE TABLE accessibility (
    place_id           INTEGER PRIMARY KEY REFERENCES places (id),
    grade              TEXT NOT NULL CHECK (grade IN ('VERIFIED', 'UNKNOWN', 'UNSUITABLE')),
    wheelchair         INTEGER CHECK (wheelchair IN (0, 1)),
    stroller           INTEGER CHECK (stroller IN (0, 1)),
    elevator           INTEGER CHECK (elevator IN (0, 1)),
    accessible_toilet  INTEGER CHECK (accessible_toilet IN (0, 1)),
    raw                TEXT CHECK (raw IS NULL OR json_valid(raw)),
    source_id          INTEGER NOT NULL REFERENCES data_sources (id)
);

CREATE TABLE stations (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    line          TEXT NOT NULL,
    latitude      REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude     REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    has_elevator  INTEGER NOT NULL CHECK (has_elevator IN (0, 1)),
    has_locker    INTEGER NOT NULL CHECK (has_locker IN (0, 1)),
    source_id     INTEGER NOT NULL REFERENCES data_sources (id)
);

CREATE TABLE station_travel (
    from_station  TEXT NOT NULL REFERENCES stations (id),
    to_station    TEXT NOT NULL REFERENCES stations (id),
    minutes       INTEGER NOT NULL CHECK (minutes >= 0),
    transfer      INTEGER NOT NULL CHECK (transfer IN (0, 1)),
    PRIMARY KEY (from_station, to_station)
);

CREATE TABLE facilities (
    id                INTEGER PRIMARY KEY,
    type              TEXT NOT NULL CHECK (type IN ('PARKING', 'LOCKER', 'BIKE', 'ELEVATOR')),
    name              TEXT,
    latitude          REAL CHECK (latitude BETWEEN -90 AND 90),
    longitude         REAL CHECK (longitude BETWEEN -180 AND 180),
    open_hours        TEXT CHECK (open_hours IS NULL OR json_valid(open_hours)),
    disabled_parking  INTEGER CHECK (disabled_parking IN (0, 1)),
    fee_info          TEXT,
    station_id        TEXT REFERENCES stations (id),
    source_id         INTEGER NOT NULL REFERENCES data_sources (id)
);

CREATE TABLE shared_courses (
    id           TEXT PRIMARY KEY,
    course_json  TEXT NOT NULL CHECK (json_valid(course_json)),
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

CREATE TABLE batch_logs (
    id             INTEGER PRIMARY KEY,
    job            TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    success_count  INTEGER,
    fail_count     INTEGER,
    message        TEXT
);
