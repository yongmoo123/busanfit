-- 부산핏 SQLite 스키마 — SDD 5.2 / 그림 5-1 (DEC-005)
-- 타입은 SQLite 실제 타입만 사용: 불리언 INTEGER 0/1, 시각 TEXT ISO 8601, JSON TEXT, UUID TEXT.
-- 새 DB 파일에 한 번 적용한다(CREATE TABLE, IF NOT EXISTS 없음). 갱신은 새 파일을 만든 뒤 교체한다.
-- places.category는 계약의 7개 값(DEC-013), 가격은 금액·기준·원문(DEC-014).
-- places.source_place_id / overview / open_hours_text, data_sources.retrieved_at은 DEC-017.
-- API place.id = "{data_sources.code}:{places.source_place_id}" (DEC-017 담당자 결정, app.data.place_id).
--   code는 적재 스크립트가 넣는 고정 값(예: tourapi-kor, tourapi-barrierfree)이고 소문자·숫자·하이픈만 허용해
--   구분자 ':'가 들어가지 않는다. source_place_id는 영문 대소문자·숫자·'_'·'-'만, 1~64자
--   (? # % / 공백 . 한글 등은 거절). 그래서 place.id는 URL 경로에 인코딩 없이 그대로 들어간다.
--   SQLite에는 정규식이 없으므로 GLOB으로 허용 문자 밖의 글자가 하나라도 있으면 거절한다.
-- SQLite는 STRICT가 아니면 INTEGER 컬럼에 소수·문자열을 그대로 저장하므로 정수 수치는 typeof로 검사한다.
-- 외래 키는 연결마다 PRAGMA foreign_keys = ON 이 필요하다(app.data.db.connect가 설정).

PRAGMA user_version = 1;

CREATE TABLE data_sources (
    id            INTEGER PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE CHECK (code <> '' AND code NOT GLOB '*[^a-z0-9-]*'),
    provider      TEXT NOT NULL,
    dataset_name  TEXT NOT NULL,
    license       TEXT,
    url           TEXT NOT NULL,
    base_date     TEXT,
    retrieved_at  TEXT NOT NULL
);

CREATE TABLE places (
    id                INTEGER PRIMARY KEY,
    source_place_id   TEXT NOT NULL CHECK (typeof(source_place_id) = 'text'
                                           AND length(source_place_id) BETWEEN 1 AND 64
                                           AND source_place_id NOT GLOB '*[^A-Za-z0-9_-]*'),
    name              TEXT NOT NULL,
    category          TEXT NOT NULL CHECK (category IN ('CAFE', 'FOOD', 'EXHIBITION', 'ATTRACTION',
                                                        'PARK', 'SHOPPING', 'OTHER')),
    area             TEXT NOT NULL,
    address           TEXT,
    latitude          REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude         REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    indoor            INTEGER CHECK (indoor IN (0, 1)),
    open_hours        TEXT CHECK (open_hours IS NULL OR json_valid(open_hours)),
    open_hours_text   TEXT,
    price_amount      INTEGER CHECK (price_amount IS NULL OR typeof(price_amount) = 'integer'),
    price_basis       TEXT CHECK (price_basis IN ('PER_PERSON', 'TOTAL')),
    price_text        TEXT,
    default_stay_min  INTEGER NOT NULL CHECK (typeof(default_stay_min) = 'integer' AND default_stay_min > 0),
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
    id            TEXT NOT NULL PRIMARY KEY,
    name          TEXT NOT NULL,
    line         TEXT NOT NULL,
    latitude      REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude     REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    has_elevator  INTEGER NOT NULL CHECK (has_elevator IN (0, 1)),
    has_locker    INTEGER NOT NULL CHECK (has_locker IN (0, 1)),
    source_id     INTEGER NOT NULL REFERENCES data_sources (id)
);

CREATE TABLE station_travel (
    from_station  TEXT NOT NULL REFERENCES stations (id),
    to_station    TEXT NOT NULL REFERENCES stations (id),
    minutes       INTEGER NOT NULL CHECK (typeof(minutes) = 'integer' AND minutes >= 0),
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
    id           TEXT NOT NULL PRIMARY KEY,
    course_json TEXT NOT NULL CHECK (json_valid(course_json)),
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

CREATE TABLE batch_logs (
    id             INTEGER PRIMARY KEY,
    job            TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    success_count  INTEGER CHECK (success_count IS NULL OR typeof(success_count) = 'integer'),
    fail_count     INTEGER CHECK (fail_count IS NULL OR typeof(fail_count) = 'integer'),
    message        TEXT
);
