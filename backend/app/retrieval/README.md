# PlaceRetriever — 이찬용 · COMP-04
FR-007·008 (#22). `domain/course.CandidateRetriever`를 구현한다. 프로필을 받아 하드 조건을 모두 통과한 장소를 거리순으로 최대 20개(`PlaceCandidate(place, distance_m)`) 돌려주고, 정보가 없어 제외한 장소의 ID·항목을 `excluded_unknown_ids`·`excluded_unknown_fields`에 담는다. 점수화(소프트 조건)는 아직 없다. SQL·공간 질의는 `data/PlaceRepository`로만 한다(DEC-005).

## 파일
- `retriever.py`: `PlaceRetriever(repository, settings=None).retrieve(profile)`
- `settings.py`: `load_retrieval_settings()` — 중심 좌표·반경·후보 상한·제외 ID 목록
- 설정 파일: `config/retrieval.json`(권역 중심 좌표, 제외 ID 파일 목록), `config/duty-free-exclusion.proposal.json`(사후면세점 ID, `pipelines/duty_free_ids.py`가 원본에서 생성)
- `retrieval.json`이 없거나, `excludedPlaceIdFiles` 키가 없거나, 목록 파일을 읽지 못하면(파일 없음·JSON 오류·`placeIds` 없음·ID 형식 오류) `RetrievalSettingsError`(`ValueError`)로 실패한다. "제외 없음"으로 바꾸지 않는다. 제외를 일부러 끄려면 `"excludedPlaceIdFiles": []`를 명시한다. 제외 없는 가상 테스트는 `RetrievalSettings`를 직접 주입한다.

## 하드 조건 (모두 통과해야 후보)
| 조건 | 기준 | 정보 없음 처리 |
|---|---|---|
| 권역·도보 반경 | 권역 중심(DEC-023 ①, 해운대해수욕장 35.159084, 129.160279)에서 `BUSANFIT_WALK_RADIUS_M`(기본 1500 m, DEC-001) 이내. Repository 질의 | — |
| 제외 카테고리 | 프로필 `excludedCategories`. Repository 질의 | — |
| 사후면세점 | 설정의 제외 ID 목록(DEC-023 ④). **DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19)** | 집계하지 않음(확정 제외) |
| 주소 | 비어 있지 않음 | `address` |
| 운영시간 | 이용 시간대의 요일에, 시간대 안에서 기본 체류시간(`default_stay_min`)만큼 머물 수 있는 영업 구간이 있음. 판정은 스케줄러와 같은 `courses/open_hours.find_slot`을 그대로 쓴다(자정 넘김·`24:00`·전날 밤 영업, 시작 시각에 초가 있으면 다음 분으로 올림) | `open_hours` NULL 또는 그 요일 키 없음 → `openHours` (DEC-023 ③, 상시 영업으로 보지 않음) |
| 이동제약 | WHEELCHAIR → `wheelchair`, STROLLER → `stroller`, INJURY → `wheelchair`(DEC-016 ③). `true`만 통과, `false`는 제외. **`grade`는 보지 않음**(DEC-015) | null 또는 무장애 행 없음 → `mobility.wheelchair`/`mobility.stroller` |
| 실내·실외 HARD | `indoor`가 요청과 같음 | `indoorPreference` |

- 확정 불가 사유(휴무, `false`, 제외 카테고리 등)가 하나라도 있는 장소는 `excluded_unknown`에 넣지 않는다. 정보를 채워도 후보가 될 수 없기 때문이다.
- `excluded_unknown_fields` 값(`openHours`, `mobility.wheelchair`, `mobility.stroller`, `address`, `indoorPreference`)은 **제안, 김영무 확인 대기**. `courses/validator.candidate_violations`의 필드 이름과 같다.
- 후보는 거리, 같으면 장소 ID 순. 상한(20)은 `config/courses.json` `maxCandidates`.
- Repository 오류(`RepositoryError`)는 그대로 올린다. 빈 후보는 "조건에 맞는 장소 없음"이다. 중심 좌표가 없는 권역은 `ValueError`.

## 사후면세점 기준 (DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19))
`pipelines/duty_free_ids.py`가 이미 받은 TourAPI 목록 원본만 읽어 `lclsSystm3 == SH040300`(분류명 "사후면세점")인 쇼핑 장소 ID를 만든다. 해운대 쇼핑 117곳 중 112곳. DB `places`에 분류 코드 칸이 없어서 ID 목록으로 제외한다. 원본을 다시 받으면 `--check`로 목록이 최신인지 확인한다.

PR #65의 기존 해운대 표본 분석 근거: 반경 1500m 안 SH040300 28곳 중 운영시간이 있는 곳은 13곳이며, 약국·체인점·마트·안경점 위주라 코스 후보로 부적합하다. 백화점 입점 매장 62곳은 모두 반경 밖이다. 기념품점(SH050300)과 시장(SH060200)은 제외되지 않는다. 백화점 본점 항목은 권역 확장 때 다시 검토한다.

같은 표본의 운영시간 NULL 103곳 = 원문은 있으나 파싱 못 한 102곳(DEC-023 기준) + 원문 자체가 없는 1곳. 원문 유무와 관계없이 구조화된 운영시간이 NULL이면 위 하드 조건 표대로 후보에서 제외한다.

## 주의
### #30 미확인 접근성 후보 풀

`RetrievalResult.unknown_accessibility_candidates`는 필요한 접근성 항목의 null 때문에만 제외된 장소를 거리 근거와 함께 전달한다. 일반 후보와 별도로 거리·ID 순 정렬 후 각각 max_candidates(기본 20)까지 전달하며, CourseService의 최종 배치 후보는 합쳐서 기존 상한을 지킨다. `excludedUnknown` 집계는 다른 정보 누락도 포함하므로 후보 풀과 구분한다.

사후면세점·권역/반경·제외 카테고리·주소·운영시간/체류 가능 구간·접근성 false·실내 HARD 등 확정 제외나 다른 미확인 조건이 있으면 별도 풀에 넣지 않는다. 동의 여부로 검색기의 일반 후보를 완화하지 않는다. #70 서버는 풀의 Repository 사실과 거리·시간·이동제약을 다시 검사하고, 동의 후 접근성 null만 조건부로 허용한다. 실제로 포함되면 CONDITIONAL과 UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds를 반환한다.

실제 DB의 별도 앱 검증 후 사용자 요청으로 #72 일반 서버의 포함 지원을 활성화했다. 일반 시작 경로의 검증은 `evaluation/courses/unknown_inclusion.py --runtime-app`으로 실행한다. capability가 true여도 사용자의 명시적 동의 전에는 이 풀을 코스에 포함하지 않는다.

- 반경이 두 곳에 있다: 검색은 `BUSANFIT_WALK_RADIUS_M`, 검증(`candidate_violations`)은 `config/courses.json` `radiusMeters`. 둘 다 기본 1500이지만, 환경변수만 늘리면 반경 밖 후보가 검증에서 빠진다.
- 앱 연결(`CourseService`에 주입, capabilities 활성화)은 이 모듈에 없다(김영무, #50 연결).
