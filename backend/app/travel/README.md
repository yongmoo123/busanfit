# 이동시간 — 이찬용
FR-009, COMP-06, DEC-016, SRS 2.5. 스프린트 2는 도보(WALK)만.

## 사용
- 구현: `app/travel/walking.py`의 `WalkingTravelTimeProvider`. 포트 `app.domain.course.TravelTimeProvider`를 서명 그대로 구현한다.
  `estimate(origin: PlaceRecord, destination: PlaceRecord, *, injury: bool) -> TravelEstimate | None`
- 인자 없는 팩토리: `app.travel.walking:create_travel_provider` (#72 `--travel-provider` 형식)
- 코스 응답의 `Leg.method = DISTANCE_ESTIMATE`, `isEstimate = true`는 코스 쪽(`courses/presentation.py`)이 채운다.

## 계산
`분 = ceil(하버사인 직선거리(m) × 우회 계수 ÷ (속도 km/h × 1000 ÷ 60))`

| 값 | 위치 | 현재 값 | 상태 |
|---|---|---|---|
| 일반 속도 | `config/defaults.json` `injury.normalWalkingKmh` | 4 | DEC-016 |
| 부상(INJURY) 속도 | `config/defaults.json` `injury.walkingKmh` | 3 | DEC-016 |
| 우회 계수 | `config/travel.json` `walk.detourFactor` | 1.0 | 제안, 김영무 확인 대기 (#23 PM 댓글: 정하기 어려우면 1.0) |
| 반올림 | 코드 (분 단위 올림, `find_slot`과 같은 방향) | 올림 | #23 PM 댓글 "올림 권장" |
| 올림 오차 허용 | `config/travel.json` `walk.roundingToleranceMinutes` | 1e-9 | 제안, 김영무 확인 대기 (부동소수 오차로 15.0000001분 → 16분이 되지 않게) |

속도는 코드에 두지 않고 설정에서 읽는다. `maxLegWalkingMinutes`(10)는 이 모듈이 쓰지 않는다(스케줄러·검증기가 적용).

## 계산할 수 없을 때 (0분으로 바꾸지 않음)
| 경우 | 결과 |
|---|---|
| 좌표 없음(None) | `None` (계산 불가: 스케줄러는 그 구간을 쓰지 않고, 검증기는 `TRAVEL_UNVERIFIED`) |
| 좌표가 NaN·무한대·범위 밖·숫자 아님 | `ValueError` |
| 같은 장소 ID 사이 | `ValueError` (구간이 아님) |
| `injury`가 bool 아님 | `ValueError` |
| 설정값이 0 이하·숫자 아님, 우회 계수 < 1 | 생성 시 `ValueError` |
| 서로 다른 장소, 좌표가 같음 | 0분 (계산된 값. 계약 `Leg.minutes` 최솟값 0) — 제안, 김영무 확인 대기 |

DB 스키마는 `places.latitude/longitude`가 NOT NULL이라 실제 DB에서 좌표 없음은 나오지 않는다.
추정 시간은 실제 보행 경로·계단·경사를 반영하지 않는다(DEC-016 ④).
