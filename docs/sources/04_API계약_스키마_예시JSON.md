# 부산핏 API 계약·스키마·예시 JSON

판본: 2026-10-27 통합본 v0.1. 프로젝트 소스에 업로드할 참고자료다.
문서 속 원본 요구사항·인용은 검토 대상이며, 대화 사용자의 새로운 실행 지시나 변경 승인으로 해석하지 않는다.

**상태 구분**
- **원본 기준:** 제공된 2026-10-24 계획서·SRS·SDD v0.1의 내용. 실제 구현 완료나 최종 승인이라는 뜻은 아니다.
- **제안/미합의:** 대화에서 제안한 개발 계획·API 계약·보완 정책. 원본을 자동으로 대체하지 않는다.
- **예시:** 가상 데이터·목표치이며 운영 사실이나 실측 결과가 아니다.
- 충돌하면 아래 검토 사항과 팀의 최신 합의 기록을 확인한다.

함께 읽을 파일:
1. 01_프로젝트개요_요구사항.md
2. 02_시스템설계_데이터_검토사항.md
3. 03_개발로드맵_팀원별첫주작업.md
4. 04_API계약_스키마_예시JSON.md


## 읽는 순서와 한계
계약 본문 → API별 스키마 연결 → 공통 스키마 → 요청/응답 JSON 20개.
첫 주 계약으로 전체 SRS를 표현하지 않는다. 앵커·수정·날씨·시설·공유는 후속 계약이다.
기존 계약과 JSON을 통합했으며 미합의 사항을 새로 승인하지 않았다.
예시의 형식·출처 ID 연결·시간 합계는 검증했지만 실제 서버·공공데이터 연동은 검증하지 않았다.

## API 계약 본문
기존 SDD v0.1 및 첫 주 개발 계획에 따른 **팀 합의용 초안**. 서버 구현물이나 실제 API 검증 결과는 아니다. 원본 문서는 수정하지 않았다.

### 통합 방식
이 파일 안에 계약·전체 공통 스키마·예시 JSON 20개를 수록했다. 별도 JSON 업로드 없이 읽을 수 있다. 원래 OpenAPI와 검증 스크립트는 개발용 묶음에 남아 있다. 아래 파일명은 예시 제목과 대응한다.

**모든 예시 장소·기관·좌표·운영시간·출처는 가상 fixture다.**
example.invalid는 의도적으로 사용할 수 없는 출처 주소다. 실제 공공데이터로 제출·사용하지 않는다.
데이터 담당자는 확인한 실제 레코드와 이용조건으로 교체해야 한다.

## 1. 첫 주 API
| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| POST /api/sessions | {} | sessionId, expiresAt, capabilities, requestId |
| POST /api/chat | sessionId, message, expectedProfileRevision | status, reply, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| PUT /api/sessions/{sessionId}/profile | expectedProfileRevision, profile | status, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| POST /api/courses | sessionId, profileRevision | status, course, suggestions, warnings, excludedUnknown, sessionExpiresAt, requestId |
| GET /api/places/{placeId} | 경로의 placeId | place, sources, warnings, requestId |

서버 주소는 로컬 예시 http://localhost:8000. 경로에 /api가 이미 포함되어 있다.
세션 생성만 HTTP 201, 나머지 성공은 200. 성공 응답은 별도 data 래퍼 없이 반환한다.

## 2. 공통 형식
- application/json, UTF-8, camelCase. 문서에 없는 필드는 거절한다.
- 날짜·시각은 offset 포함 RFC3339. 예: 2026-11-06T13:00:00+09:00. 표시와 상대 날짜 해석은 Asia/Seoul.
- 시간 범위는 startAt < endAt. 첫 주에는 같은 현지 날짜만 지원한다. 자정 넘는 요청은 422 INVALID_PROFILE.
- 시간은 정수 분, 금액은 정수 원(KRW). latitude=위도, longitude=경도.
- ID는 불투명 문자열로 취급한다. sessionId/course.id/requestId는 UUID, place.id는 문자열.
- 모든 필드는 스키마대로 포함한다. 정보 없음=null, 빈 목록=[], 확인된 부정=false. null을 false·0·무료로 바꾸지 않는다.
- 모든 응답의 requestId는 실제 서버에서 새로 만든다. 고정 예시 ID와 날짜는 테스트 전용이다.
- FastAPI 기본 422 형식도 아래 공통 ErrorResponse로 변환한다.

## 3. 세션·동시 요청
- 세션 비활동 만료는 30분. 유효한 세션 작업이 활동 시간을 갱신하고 sessionExpiresAt을 반환한다. 공개 장소 조회는 갱신하지 않는다.
- sessionId는 비밀 토큰이다. 실제 배포는 HTTPS. 민감한 응답은 Cache-Control: no-store.
- 프론트는 세션·대화·프로필을 메모리로 관리하고 브라우저 영구 저장소에 저장하지 않는다.
- URL 접근 로그에서도 sessionId를 마스킹한다. 원문·프로필·건강 정보를 로그·DB에 남기지 않는다.
- 생성 직후 내부 profileRevision=0. chat/PUT 성공마다 원자적으로 1 증가한다. 실패는 프로필·revision·대화 상태를 변경하지 않는다.
- chat/PUT의 expectedProfileRevision이 서버와 다르면 409. 코스 요청 profileRevision도 서버 최신값과 일치해야 한다.
- 생성 중 프로필이 바뀌면 이전 결과를 최신 코스처럼 반환하지 않고 409 처리한다.
- 첫 주 프론트는 한 세션의 요청을 순차 처리하고 전송 중 버튼을 잠근다.
- 프로필 GET은 이번 범위에 없다. 409이면 대기 중인 성공 응답을 먼저 반영한다. 최신 상태를 복구할 수 없으면 새 세션을 시작한다.
- 응답 유실 시 변경 요청을 무조건 자동 재전송하지 않는다.

## 4. 프로필 의미
각 조건은 {value, source, strength}다.
- source: USER / DEFAULT / UNSET. null 값과 UNSET은 서로 대응해야 한다.
- strength: HARD(필수) / SOFT(선호).
- area/timeWindow는 코스 생성 필수이고 HARD다.
- mobility=null은 미입력. []는 사용자가 이동 제약이 없다고 명시한 경우다. 미입력을 제약 없음으로 확정하지 않는다.
- “실내 위주”는 SOFT, “실외는 절대 안 돼”는 HARD. 단어 하나만 보고 부정 표현을 오해하지 않는다.
- companions.hasInfant=true만으로 유모차 제약을 자동 확정하지 않는다.
- budget은 amount, currency, basis(PER_PERSON/TOTAL), includes(ADMISSION/FOOD/TRANSPORT)를 함께 저장한다.
- 첫 주 예시 기본 이동수단은 도보(DEFAULT)이며 카드에 표시한다. 최종 기본값은 SRS와 합의해 맞춘다.
- chat은 언급된 조건만 기존 프로필에 반영한다. “카페는 빼줘”가 기존 시간을 지우면 안 된다.
- PUT은 전체 교체다. 삭제할 값은 null/UNSET으로 명시한다. 카드에서 바꾼 값은 USER로 표시한다.
- 서버는 클라이언트의 source/strength도 검증한다. 지역·시간의 HARD를 임의로 낮추지 못하게 한다.
- NEEDS_INPUT: 생성 필수 정보가 부족하다. questions는 1~2개.
- READY: 생성 요청이 가능한 구조이며 questions=[]. 후보 존재나 코스 성공을 보장하지 않는다.
- 질문은 최대 2개씩 한다. 불확실한 중요한 조건을 기본값으로 덮어쓰지 않는다.

## 5. capabilities와 첫 주 지원
예시 capabilities는 HAEUNDAE/WALK 및 area,timeWindow,transport,indoorPreference,companions,excludedCategories를 지원한다.
budget/mobility/preferenceTags도 최종 프로필 모양에는 있으나 예시 서버의 첫 주 활성 조건 지원 범위에는 없다.
- 미지원 필드가 null/빈 목록이면 미설정으로 취급할 수 있다.
- 비어 있지 않은 미지원 조건을 요청하면 HARD/SOFT 모두 422 UNSUPPORTED_CONSTRAINT.
- AI가 미지원 조건을 인식하면 요청 전체를 저장하지 않고 관련 필드를 오류 details로 반환한다.
- includeUnknownAccessibility는 첫 주 false만 허용한다. true 요청은 422.
- 권역/이동수단도 capabilities로 검증한다. 구현되지 않은 조건을 지원한다고 표시하지 않는다.
- 이는 최종 SRS Must 요구사항의 삭제가 아니다. 이후 검증을 마친 기능부터 지원 범위를 넓힌다.

## 6. 코스 의미·검증
- SUCCESS는 course가 존재, INSUFFICIENT_PLACES는 HTTP 200 + course=null.
- 첫 주 후보가 두 곳 미만이면 후보 부족이다. 시간 안에 못 넣는 장소를 무리하게 채우지 않는다.
- suggestions는 최대 3개, 첫 주 type=EDIT_PROFILE만 허용. 클릭은 조건 입력 카드를 열며 자동으로 조건을 변경하지 않는다.
- course.availableWindow는 사용자의 허용 시간, startAt/endAt은 실제 첫 방문 시작/마지막 방문 종료. 시간을 모두 채울 필요는 없다.
- items.order는 1부터 연속, item.id는 코스 내 고유값. place.id와 구분한다.
- N개 방문이면 legs는 N-1개이며 인접 item.id를 연결한다.
- 다음 방문 시작 >= 이전 방문 종료 + 이동시간. 남는 차이는 대기시간이다.
- totalMinutes = totalStayMinutes + totalTravelMinutes + totalWaitingMinutes = 종료-시작.
- 출발지/귀가 목적지는 첫 주에 받지 않는다. 첫 장소 이전과 마지막 장소 이후 이동은 합계에서 제외한다고 화면에 표시한다.
- 지도 연결선은 방문 순서다. DISTANCE_ESTIMATE를 실제 보행 경로로 표현하지 않는다.
- 이동시간의 method/isEstimate 및 경로 접근성 미검증 상태를 표시한다.
- price.status=UNKNOWN이면 amount=null, basis=UNKNOWN. KNOWN이면 금액 및 PER_PERSON/TOTAL 기준이 필요하다.
- 일부 가격의 합을 전체 예산으로 표시하지 않는다. 가격 수준 등급만으로 원 단위 예산 충족을 주장하지 않는다.
- openHours.UNKNOWN이면 description=null. KNOWN의 문자열은 표시용이며 백엔드는 별도 정규화한 날짜·요일별 운영 구간으로 검증한다.
- HARD 판단에 필요한 운영시간·가격·접근성 정보가 없으면 충족으로 인정하지 않는다.
- accessibility 항목은 true/false/null, VERIFIED는 관련 근거가 있어야 한다. 시설 정보가 전체 경로 접근성을 보장하지 않는다.
- mobility 미입력 일반 코스에는 접근성 UNKNOWN 장소가 포함될 수 있다. 이동제약을 확인한 코스로 표시하면 안 된다.
- validation.PASSED는 checkedHardConstraints에 나열한 조건이 데이터와 추정 방식 기준으로 통과했다는 의미다.
- unverifiedFields가 활성 HARD 조건과 겹치면 PASSED 금지.
- CONDITIONAL은 추후 미확인 정보 포함 동의 기능의 예약 값이다. 첫 주에는 반환하지 않으며 HARD 위반 우회 수단이 아니다.
- excludedUnknown.count는 필수 판단 정보 부족으로 제외한 고유 장소 수. fields는 이유 목록이다.
- sourceIds/evidence.sourceId는 응답 sources에 모두 존재해야 한다. sources의 id는 중복하지 않는다.
- license/baseDate=null은 미확인 표현용이다. 실제 공개 전 이용조건을 확인해야 한다. 제공 기준일과 retrievedAt(조회일)을 구분한다.
- 출처는 시스템이 DB에서 붙인다. LLM이 가격·시간·출처를 만들어내지 않는다.
- 추천 이유 생성 실패는 TEMPLATE 설명과 warnings로 처리할 수 있다.

## 7. 오류
형식: {"error":{"code":"...","message":"...","retryable":false,"details":[{"field":"...","reason":"..."}]},"requestId":"UUID"}
| HTTP | code | 처리 |
|---|---|---|
| 400 | INVALID_REQUEST | 잘못된 JSON |
| 404 | NOT_FOUND | 장소 없음 |
| 409 | REVISION_CONFLICT | 최신 조건 확인 |
| 410 | SESSION_EXPIRED | 새 세션 안내 |
| 422 | INVALID_REQUEST / INVALID_PROFILE / PROFILE_INCOMPLETE / UNSUPPORTED_CONSTRAINT | 해당 필드 수정 |
| 429 | RATE_LIMITED | Retry-After 헤더(초)를 참고해 재시도 |
| 503 | AI_UNAVAILABLE | 조건 카드 직접 입력/재시도 |
| 500 | INTERNAL_ERROR | 일반 오류 안내, 내부 스택 미노출 |

details에 민감한 원문을 넣지 않는다.
첫 주 세션당 분당 20회 제한, 세션 생성은 별도 IP 제한을 적용한다.
retryable=true는 즉시 자동 재전송하라는 뜻이 아니다.
AI 해석 실패 시 하드 조건을 지우고 일반 코스를 만들지 않는다.

## 8. 예시 사용 순서
기본 흐름:
1. 01-session.request → 01-session.response. 내부 revision=0.
2. 02-chat.request(expected=0) → 02-chat.ready.response(revision=1).
3. 04-course.request(revision=1) → 04-course.success.response.
4. 각 place.id로 상세 요청 → 05-place.response 형식.

조건 카드 수정 분기:
1~2 이후 03-profile.request(expected=1) → 03-profile.response(revision=2).
이후 코스 요청의 profileRevision도 2로 바꾼다. 제공된 04-course 파일은 수정 없는 기본 흐름용이다.
needs-input/insufficient/오류 파일은 서로 독립된 상태 예시다.
실제 서버는 고정 예시의 날짜/UUID/requestId를 그대로 반환하면 안 된다.

## 9. 기존 SDD와의 차이 및 후속 범위
경로는 유지했다. {id} 이름만 {sessionId}로 명확히 했다.
추가 합의 사항: 프로필 revision, capabilities, 상태·오류 형식, nullable 규칙, 여러 출처 sources/sourceIds, 미확인 가격/접근성, 도보 기본값을 쓰는 첫 주 축소 범위.
단일 source에서 여러 sources로 확장했으므로 DB 매핑도 함께 합의한다.
유보 API(이번 OpenAPI에 등록하지 않음):
- POST /api/courses/{courseId}/adjust
- GET /api/facilities
- POST /api/courses/{courseId}/share
- GET /api/share/{shareId}
- 관리자 배치 CLI
특히 adjust는 변경 후 시간 유지·재검증 정책을 합의한 뒤 정의한다.

## 10. 팀원별 시작점
- 김영무: 스키마 기반 요청/응답 모델, 예외 핸들러, 세션 revision 검사.
- 이찬용: Place/Source/Accessibility 형식에 맞춘 실제 DB 변환, 운영시간 내부 정규화.
- 배진호: examples로 mock 연결, 상태별 화면 분기, 지원 범위 표시.
- 김세민: 예시별 검수 시나리오, 실제 데이터·출처 확인, SRS/SDD 변경 기록.
GitHub에 합의 버전을 커밋하고 필드·enum·상태 의미 변경은 프론트·백엔드 공동 PR 검토로 진행한다.


## API별 스키마 연결

| 작업 | 요청 스키마 | 성공 상태 | 응답 스키마 |
|---|---|---|---|
| POST /api/sessions | SessionRequest | 201 | SessionResponse |
| POST /api/chat | ChatRequest | 200 | ChatResponse |
| PUT /api/sessions/{sessionId}/profile | ProfileUpdateRequest | 200 | ProfileResponse |
| POST /api/courses | CourseRequest | 200 | CourseResponse |
| GET /api/places/{placeId} | 없음 | 200 | PlaceResponse |

## 공통 스키마 전체
JSON Schema(OpenAPI 3.1). $ref는 아래 components.schemas 이름을 가리킨다. 의미 제약은 계약 본문도 함께 적용한다.

~~~json
{
  "components": {
    "schemas": {
      "Warning": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "message": {
            "type": "string"
          },
          "placeIds": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "code",
          "message",
          "placeIds"
        ],
        "additionalProperties": false
      },
      "Source": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "provider": {
            "type": "string"
          },
          "datasetName": {
            "type": "string"
          },
          "url": {
            "type": "string",
            "format": "uri"
          },
          "license": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          },
          "baseDate": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ]
          },
          "retrievedAt": {
            "type": "string",
            "format": "date-time"
          }
        },
        "required": [
          "id",
          "provider",
          "datasetName",
          "url",
          "license",
          "baseDate",
          "retrievedAt"
        ],
        "additionalProperties": false
      },
      "TimeWindow": {
        "type": "object",
        "properties": {
          "startAt": {
            "type": "string",
            "format": "date-time"
          },
          "endAt": {
            "type": "string",
            "format": "date-time"
          }
        },
        "required": [
          "startAt",
          "endAt"
        ],
        "additionalProperties": false
      },
      "Budget": {
        "type": "object",
        "properties": {
          "amount": {
            "type": "integer",
            "minimum": 0
          },
          "currency": {
            "type": "string",
            "enum": [
              "KRW"
            ]
          },
          "basis": {
            "type": "string",
            "enum": [
              "PER_PERSON",
              "TOTAL"
            ]
          },
          "includes": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "ADMISSION",
                "FOOD",
                "TRANSPORT"
              ]
            },
            "minItems": 1,
            "uniqueItems": true
          }
        },
        "required": [
          "amount",
          "currency",
          "basis",
          "includes"
        ],
        "additionalProperties": false
      },
      "Companions": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "SOLO",
              "FRIENDS",
              "COUPLE",
              "FAMILY",
              "OTHER"
            ]
          },
          "count": {
            "type": "integer",
            "minimum": 1
          },
          "hasInfant": {
            "type": "boolean"
          }
        },
        "required": [
          "type",
          "count",
          "hasInfant"
        ],
        "additionalProperties": false
      },
      "Profile": {
        "type": "object",
        "properties": {
          "area": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "string",
                    "enum": [
                      "HAEUNDAE",
                      "SEOMYEON",
                      "GWANGALLI",
                      "NAMPO"
                    ]
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "timeWindow": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/TimeWindow"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "transport": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "string",
                    "enum": [
                      "WALK",
                      "PUBLIC",
                      "CAR"
                    ]
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "mobility": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "enum": [
                        "WHEELCHAIR",
                        "STROLLER",
                        "INJURY"
                      ]
                    },
                    "uniqueItems": true
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "budget": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/Budget"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "indoorPreference": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "string",
                    "enum": [
                      "INDOOR",
                      "OUTDOOR",
                      "ANY"
                    ]
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "companions": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/Companions"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "excludedCategories": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "enum": [
                        "CAFE",
                        "FOOD",
                        "EXHIBITION",
                        "ATTRACTION",
                        "PARK",
                        "SHOPPING",
                        "OTHER"
                      ]
                    },
                    "uniqueItems": true
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "preferenceTags": {
            "type": "object",
            "properties": {
              "value": {
                "anyOf": [
                  {
                    "type": "array",
                    "items": {
                      "type": "string"
                    },
                    "uniqueItems": true
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "source": {
                "type": "string",
                "enum": [
                  "USER",
                  "DEFAULT",
                  "UNSET"
                ]
              },
              "strength": {
                "type": "string",
                "enum": [
                  "HARD",
                  "SOFT"
                ]
              }
            },
            "required": [
              "value",
              "source",
              "strength"
            ],
            "additionalProperties": false
          },
          "includeUnknownAccessibility": {
            "type": "boolean"
          }
        },
        "required": [
          "area",
          "timeWindow",
          "transport",
          "mobility",
          "budget",
          "indoorPreference",
          "companions",
          "excludedCategories",
          "preferenceTags",
          "includeUnknownAccessibility"
        ],
        "additionalProperties": false
      },
      "Capabilities": {
        "type": "object",
        "properties": {
          "supportedAreas": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "HAEUNDAE",
                "SEOMYEON",
                "GWANGALLI",
                "NAMPO"
              ]
            }
          },
          "supportedTransports": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "WALK",
                "PUBLIC",
                "CAR"
              ]
            }
          },
          "supportedProfileFields": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": [
                "area",
                "timeWindow",
                "transport",
                "mobility",
                "budget",
                "indoorPreference",
                "companions",
                "excludedCategories",
                "preferenceTags"
              ]
            }
          },
          "supportsUnknownAccessibilityInclusion": {
            "type": "boolean"
          },
          "supportsCourseAdjustment": {
            "type": "boolean"
          },
          "supportsWeather": {
            "type": "boolean"
          }
        },
        "required": [
          "supportedAreas",
          "supportedTransports",
          "supportedProfileFields",
          "supportsUnknownAccessibilityInclusion",
          "supportsCourseAdjustment",
          "supportsWeather"
        ],
        "additionalProperties": false
      },
      "Question": {
        "type": "object",
        "properties": {
          "field": {
            "type": "string",
            "enum": [
              "area",
              "timeWindow",
              "transport",
              "mobility",
              "budget",
              "indoorPreference",
              "companions",
              "excludedCategories",
              "preferenceTags"
            ]
          },
          "message": {
            "type": "string"
          }
        },
        "required": [
          "field",
          "message"
        ],
        "additionalProperties": false
      },
      "ErrorDetail": {
        "type": "object",
        "properties": {
          "field": {
            "type": "string"
          },
          "reason": {
            "type": "string"
          }
        },
        "required": [
          "field",
          "reason"
        ],
        "additionalProperties": false
      },
      "ErrorResponse": {
        "type": "object",
        "properties": {
          "error": {
            "type": "object",
            "properties": {
              "code": {
                "type": "string",
                "enum": [
                  "INVALID_REQUEST",
                  "INVALID_PROFILE",
                  "PROFILE_INCOMPLETE",
                  "UNSUPPORTED_CONSTRAINT",
                  "SESSION_EXPIRED",
                  "REVISION_CONFLICT",
                  "NOT_FOUND",
                  "RATE_LIMITED",
                  "AI_UNAVAILABLE",
                  "INTERNAL_ERROR"
                ]
              },
              "message": {
                "type": "string"
              },
              "retryable": {
                "type": "boolean"
              },
              "details": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ErrorDetail"
                }
              }
            },
            "required": [
              "code",
              "message",
              "retryable",
              "details"
            ],
            "additionalProperties": false
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "error",
          "requestId"
        ],
        "additionalProperties": false
      },
      "SessionRequest": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": false
      },
      "SessionResponse": {
        "type": "object",
        "properties": {
          "sessionId": {
            "type": "string",
            "format": "uuid"
          },
          "expiresAt": {
            "type": "string",
            "format": "date-time"
          },
          "capabilities": {
            "$ref": "#/components/schemas/Capabilities"
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "sessionId",
          "expiresAt",
          "capabilities",
          "requestId"
        ],
        "additionalProperties": false
      },
      "ChatRequest": {
        "type": "object",
        "properties": {
          "sessionId": {
            "type": "string",
            "format": "uuid"
          },
          "message": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000
          },
          "expectedProfileRevision": {
            "type": "integer",
            "minimum": 0
          }
        },
        "required": [
          "sessionId",
          "message",
          "expectedProfileRevision"
        ],
        "additionalProperties": false
      },
      "ChatResponse": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "NEEDS_INPUT",
              "READY"
            ]
          },
          "reply": {
            "type": "string"
          },
          "profile": {
            "$ref": "#/components/schemas/Profile"
          },
          "profileRevision": {
            "type": "integer",
            "minimum": 1
          },
          "questions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Question"
            },
            "maxItems": 2
          },
          "warnings": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Warning"
            }
          },
          "sessionExpiresAt": {
            "type": "string",
            "format": "date-time"
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "status",
          "reply",
          "profile",
          "profileRevision",
          "questions",
          "warnings",
          "sessionExpiresAt",
          "requestId"
        ],
        "additionalProperties": false
      },
      "ProfileUpdateRequest": {
        "type": "object",
        "properties": {
          "expectedProfileRevision": {
            "type": "integer",
            "minimum": 0
          },
          "profile": {
            "$ref": "#/components/schemas/Profile"
          }
        },
        "required": [
          "expectedProfileRevision",
          "profile"
        ],
        "additionalProperties": false
      },
      "ProfileResponse": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "NEEDS_INPUT",
              "READY"
            ]
          },
          "profile": {
            "$ref": "#/components/schemas/Profile"
          },
          "profileRevision": {
            "type": "integer",
            "minimum": 1
          },
          "questions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Question"
            },
            "maxItems": 2
          },
          "warnings": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Warning"
            }
          },
          "sessionExpiresAt": {
            "type": "string",
            "format": "date-time"
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "status",
          "profile",
          "profileRevision",
          "questions",
          "warnings",
          "sessionExpiresAt",
          "requestId"
        ],
        "additionalProperties": false
      },
      "CourseRequest": {
        "type": "object",
        "properties": {
          "sessionId": {
            "type": "string",
            "format": "uuid"
          },
          "profileRevision": {
            "type": "integer",
            "minimum": 1
          }
        },
        "required": [
          "sessionId",
          "profileRevision"
        ],
        "additionalProperties": false
      },
      "Coordinates": {
        "type": "object",
        "properties": {
          "latitude": {
            "type": "number",
            "minimum": -90,
            "maximum": 90
          },
          "longitude": {
            "type": "number",
            "minimum": -180,
            "maximum": 180
          }
        },
        "required": [
          "latitude",
          "longitude"
        ],
        "additionalProperties": false
      },
      "Price": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "KNOWN",
              "UNKNOWN"
            ]
          },
          "amount": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0
              },
              {
                "type": "null"
              }
            ]
          },
          "currency": {
            "type": "string",
            "enum": [
              "KRW"
            ]
          },
          "basis": {
            "type": "string",
            "enum": [
              "PER_PERSON",
              "TOTAL",
              "UNKNOWN"
            ]
          }
        },
        "required": [
          "status",
          "amount",
          "currency",
          "basis"
        ],
        "additionalProperties": false
      },
      "Accessibility": {
        "type": "object",
        "properties": {
          "grade": {
            "type": "string",
            "enum": [
              "VERIFIED",
              "UNKNOWN",
              "UNSUITABLE"
            ]
          },
          "wheelchair": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "stroller": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "elevator": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "accessibleToilet": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "field": {
                  "type": "string",
                  "enum": [
                    "wheelchair",
                    "stroller",
                    "elevator",
                    "accessibleToilet"
                  ]
                },
                "sourceId": {
                  "type": "string"
                },
                "note": {
                  "type": "string"
                }
              },
              "required": [
                "field",
                "sourceId",
                "note"
              ],
              "additionalProperties": false
            }
          }
        },
        "required": [
          "grade",
          "wheelchair",
          "stroller",
          "elevator",
          "accessibleToilet",
          "evidence"
        ],
        "additionalProperties": false
      },
      "OpenHours": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "KNOWN",
              "UNKNOWN"
            ]
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          }
        },
        "required": [
          "status",
          "description"
        ],
        "additionalProperties": false
      },
      "Place": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "category": {
            "type": "string",
            "enum": [
              "CAFE",
              "FOOD",
              "EXHIBITION",
              "ATTRACTION",
              "PARK",
              "SHOPPING",
              "OTHER"
            ]
          },
          "area": {
            "type": "string",
            "enum": [
              "HAEUNDAE",
              "SEOMYEON",
              "GWANGALLI",
              "NAMPO"
            ]
          },
          "address": {
            "type": "string"
          },
          "coordinates": {
            "$ref": "#/components/schemas/Coordinates"
          },
          "indoor": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ]
          },
          "openHours": {
            "$ref": "#/components/schemas/OpenHours"
          },
          "price": {
            "$ref": "#/components/schemas/Price"
          },
          "defaultStayMinutes": {
            "type": "integer",
            "minimum": 1
          },
          "accessibility": {
            "$ref": "#/components/schemas/Accessibility"
          },
          "sourceIds": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "minItems": 1,
            "uniqueItems": true
          }
        },
        "required": [
          "id",
          "name",
          "category",
          "area",
          "address",
          "coordinates",
          "indoor",
          "openHours",
          "price",
          "defaultStayMinutes",
          "accessibility",
          "sourceIds"
        ],
        "additionalProperties": false
      },
      "PlaceResponse": {
        "type": "object",
        "properties": {
          "place": {
            "$ref": "#/components/schemas/Place"
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Source"
            },
            "minItems": 1
          },
          "warnings": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Warning"
            }
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "place",
          "sources",
          "warnings",
          "requestId"
        ],
        "additionalProperties": false
      },
      "CourseItem": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "order": {
            "type": "integer",
            "minimum": 1
          },
          "place": {
            "$ref": "#/components/schemas/Place"
          },
          "startAt": {
            "type": "string",
            "format": "date-time"
          },
          "endAt": {
            "type": "string",
            "format": "date-time"
          },
          "stayMinutes": {
            "type": "integer",
            "minimum": 1
          },
          "reason": {
            "type": "string"
          },
          "reasonMethod": {
            "type": "string",
            "enum": [
              "LLM",
              "TEMPLATE"
            ]
          },
          "isAnchor": {
            "type": "boolean"
          }
        },
        "required": [
          "id",
          "order",
          "place",
          "startAt",
          "endAt",
          "stayMinutes",
          "reason",
          "reasonMethod",
          "isAnchor"
        ],
        "additionalProperties": false
      },
      "Leg": {
        "type": "object",
        "properties": {
          "fromItemId": {
            "type": "string"
          },
          "toItemId": {
            "type": "string"
          },
          "mode": {
            "type": "string",
            "enum": [
              "WALK",
              "PUBLIC",
              "CAR"
            ]
          },
          "minutes": {
            "type": "integer",
            "minimum": 0
          },
          "method": {
            "type": "string",
            "enum": [
              "DISTANCE_ESTIMATE",
              "STATION_DATA",
              "ROUTING_API"
            ]
          },
          "isEstimate": {
            "type": "boolean"
          }
        },
        "required": [
          "fromItemId",
          "toItemId",
          "mode",
          "minutes",
          "method",
          "isEstimate"
        ],
        "additionalProperties": false
      },
      "Validation": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "PASSED",
              "CONDITIONAL"
            ]
          },
          "checkedHardConstraints": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "unverifiedFields": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "routeAccessibility": {
            "type": "string",
            "enum": [
              "UNVERIFIED",
              "VERIFIED"
            ]
          }
        },
        "required": [
          "status",
          "checkedHardConstraints",
          "unverifiedFields",
          "routeAccessibility"
        ],
        "additionalProperties": false
      },
      "Course": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid"
          },
          "profileRevision": {
            "type": "integer",
            "minimum": 1
          },
          "createdAt": {
            "type": "string",
            "format": "date-time"
          },
          "availableWindow": {
            "$ref": "#/components/schemas/TimeWindow"
          },
          "startAt": {
            "type": "string",
            "format": "date-time"
          },
          "endAt": {
            "type": "string",
            "format": "date-time"
          },
          "items": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/CourseItem"
            },
            "minItems": 2,
            "maxItems": 6
          },
          "legs": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Leg"
            }
          },
          "summary": {
            "type": "object",
            "properties": {
              "totalStayMinutes": {
                "type": "integer",
                "minimum": 0
              },
              "totalTravelMinutes": {
                "type": "integer",
                "minimum": 0
              },
              "totalWaitingMinutes": {
                "type": "integer",
                "minimum": 0
              },
              "totalMinutes": {
                "type": "integer",
                "minimum": 0
              },
              "estimatedCost": {
                "$ref": "#/components/schemas/Price"
              }
            },
            "required": [
              "totalStayMinutes",
              "totalTravelMinutes",
              "totalWaitingMinutes",
              "totalMinutes",
              "estimatedCost"
            ],
            "additionalProperties": false
          },
          "validation": {
            "$ref": "#/components/schemas/Validation"
          },
          "sources": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Source"
            },
            "minItems": 1
          }
        },
        "required": [
          "id",
          "profileRevision",
          "createdAt",
          "availableWindow",
          "startAt",
          "endAt",
          "items",
          "legs",
          "summary",
          "validation",
          "sources"
        ],
        "additionalProperties": false
      },
      "Suggestion": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "type": {
            "type": "string",
            "enum": [
              "EDIT_PROFILE"
            ]
          },
          "label": {
            "type": "string"
          },
          "field": {
            "type": "string",
            "enum": [
              "area",
              "timeWindow",
              "transport",
              "mobility",
              "budget",
              "indoorPreference",
              "companions",
              "excludedCategories",
              "preferenceTags"
            ]
          }
        },
        "required": [
          "id",
          "type",
          "label",
          "field"
        ],
        "additionalProperties": false
      },
      "CourseSuccess": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "SUCCESS"
            ]
          },
          "course": {
            "$ref": "#/components/schemas/Course"
          },
          "suggestions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Suggestion"
            },
            "maxItems": 3
          },
          "warnings": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Warning"
            }
          },
          "excludedUnknown": {
            "type": "object",
            "properties": {
              "count": {
                "type": "integer",
                "minimum": 0
              },
              "fields": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "count",
              "fields"
            ],
            "additionalProperties": false
          },
          "sessionExpiresAt": {
            "type": "string",
            "format": "date-time"
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "status",
          "course",
          "suggestions",
          "warnings",
          "excludedUnknown",
          "sessionExpiresAt",
          "requestId"
        ],
        "additionalProperties": false
      },
      "CourseInsufficient": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "INSUFFICIENT_PLACES"
            ]
          },
          "course": {
            "type": "null"
          },
          "suggestions": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Suggestion"
            },
            "maxItems": 3
          },
          "warnings": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Warning"
            }
          },
          "excludedUnknown": {
            "type": "object",
            "properties": {
              "count": {
                "type": "integer",
                "minimum": 0
              },
              "fields": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "count",
              "fields"
            ],
            "additionalProperties": false
          },
          "sessionExpiresAt": {
            "type": "string",
            "format": "date-time"
          },
          "requestId": {
            "type": "string",
            "format": "uuid"
          }
        },
        "required": [
          "status",
          "course",
          "suggestions",
          "warnings",
          "excludedUnknown",
          "sessionExpiresAt",
          "requestId"
        ],
        "additionalProperties": false
      },
      "CourseResponse": {
        "oneOf": [
          {
            "$ref": "#/components/schemas/CourseSuccess"
          },
          {
            "$ref": "#/components/schemas/CourseInsufficient"
          }
        ]
      }
    }
  }
}
~~~

## 요청·응답 예시 20개
정상 흐름과 오류 흐름은 독립 예시다.

### 01-session.request.json
대응 스키마: SessionRequest

~~~json
{}
~~~

### 01-session.response.json
대응 스키마: SessionResponse

~~~json
{
  "sessionId": "11111111-1111-4111-8111-111111111111",
  "expiresAt": "2026-11-05T10:30:00+09:00",
  "capabilities": {
    "supportedAreas": [
      "HAEUNDAE"
    ],
    "supportedTransports": [
      "WALK"
    ],
    "supportedProfileFields": [
      "area",
      "timeWindow",
      "transport",
      "indoorPreference",
      "companions",
      "excludedCategories"
    ],
    "supportsUnknownAccessibilityInclusion": false,
    "supportsCourseAdjustment": false,
    "supportsWeather": false
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 02-chat.request.json
대응 스키마: ChatRequest

~~~json
{
  "sessionId": "11111111-1111-4111-8111-111111111111",
  "message": "2026년 11월 6일 해운대에서 오후 1시부터 5시까지 친구와 둘이 실내 위주로 놀고 싶어.",
  "expectedProfileRevision": 0
}
~~~

### 02-chat.ready.response.json
대응 스키마: ChatResponse

~~~json
{
  "status": "READY",
  "reply": "조건을 확인해 주세요. 이동수단은 도보를 기본값으로 적용했어요.",
  "profile": {
    "area": {
      "value": "HAEUNDAE",
      "source": "USER",
      "strength": "HARD"
    },
    "timeWindow": {
      "value": {
        "startAt": "2026-11-06T13:00:00+09:00",
        "endAt": "2026-11-06T17:00:00+09:00"
      },
      "source": "USER",
      "strength": "HARD"
    },
    "transport": {
      "value": "WALK",
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "mobility": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "budget": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "indoorPreference": {
      "value": "INDOOR",
      "source": "USER",
      "strength": "SOFT"
    },
    "companions": {
      "value": {
        "type": "FRIENDS",
        "count": 2,
        "hasInfant": false
      },
      "source": "USER",
      "strength": "SOFT"
    },
    "excludedCategories": {
      "value": [],
      "source": "DEFAULT",
      "strength": "HARD"
    },
    "preferenceTags": {
      "value": [],
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "includeUnknownAccessibility": false
  },
  "profileRevision": 1,
  "questions": [],
  "warnings": [],
  "sessionExpiresAt": "2026-11-05T10:30:00+09:00",
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 02-chat.needs-input.response.json
대응 스키마: ChatResponse

~~~json
{
  "status": "NEEDS_INPUT",
  "reply": "방문 날짜와 이용할 시간을 알려주세요.",
  "profile": {
    "area": {
      "value": "HAEUNDAE",
      "source": "USER",
      "strength": "HARD"
    },
    "timeWindow": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "transport": {
      "value": "WALK",
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "mobility": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "budget": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "indoorPreference": {
      "value": "INDOOR",
      "source": "USER",
      "strength": "SOFT"
    },
    "companions": {
      "value": {
        "type": "FRIENDS",
        "count": 2,
        "hasInfant": false
      },
      "source": "USER",
      "strength": "SOFT"
    },
    "excludedCategories": {
      "value": [],
      "source": "DEFAULT",
      "strength": "HARD"
    },
    "preferenceTags": {
      "value": [],
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "includeUnknownAccessibility": false
  },
  "profileRevision": 1,
  "questions": [
    {
      "field": "timeWindow",
      "message": "언제 방문하고, 몇 시부터 몇 시까지 이용하시나요?"
    }
  ],
  "warnings": [],
  "sessionExpiresAt": "2026-11-05T10:30:00+09:00",
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 03-profile.request.json
대응 스키마: ProfileUpdateRequest

~~~json
{
  "expectedProfileRevision": 1,
  "profile": {
    "area": {
      "value": "HAEUNDAE",
      "source": "USER",
      "strength": "HARD"
    },
    "timeWindow": {
      "value": {
        "startAt": "2026-11-06T13:00:00+09:00",
        "endAt": "2026-11-06T17:00:00+09:00"
      },
      "source": "USER",
      "strength": "HARD"
    },
    "transport": {
      "value": "WALK",
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "mobility": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "budget": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "indoorPreference": {
      "value": "INDOOR",
      "source": "USER",
      "strength": "HARD"
    },
    "companions": {
      "value": {
        "type": "FRIENDS",
        "count": 2,
        "hasInfant": false
      },
      "source": "USER",
      "strength": "SOFT"
    },
    "excludedCategories": {
      "value": [],
      "source": "DEFAULT",
      "strength": "HARD"
    },
    "preferenceTags": {
      "value": [],
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "includeUnknownAccessibility": false
  }
}
~~~

### 03-profile.response.json
대응 스키마: ProfileResponse

~~~json
{
  "status": "READY",
  "profile": {
    "area": {
      "value": "HAEUNDAE",
      "source": "USER",
      "strength": "HARD"
    },
    "timeWindow": {
      "value": {
        "startAt": "2026-11-06T13:00:00+09:00",
        "endAt": "2026-11-06T17:00:00+09:00"
      },
      "source": "USER",
      "strength": "HARD"
    },
    "transport": {
      "value": "WALK",
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "mobility": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "budget": {
      "value": null,
      "source": "UNSET",
      "strength": "HARD"
    },
    "indoorPreference": {
      "value": "INDOOR",
      "source": "USER",
      "strength": "HARD"
    },
    "companions": {
      "value": {
        "type": "FRIENDS",
        "count": 2,
        "hasInfant": false
      },
      "source": "USER",
      "strength": "SOFT"
    },
    "excludedCategories": {
      "value": [],
      "source": "DEFAULT",
      "strength": "HARD"
    },
    "preferenceTags": {
      "value": [],
      "source": "DEFAULT",
      "strength": "SOFT"
    },
    "includeUnknownAccessibility": false
  },
  "profileRevision": 2,
  "questions": [],
  "warnings": [],
  "sessionExpiresAt": "2026-11-05T10:30:00+09:00",
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 04-course.request.json
대응 스키마: CourseRequest

~~~json
{
  "sessionId": "11111111-1111-4111-8111-111111111111",
  "profileRevision": 1
}
~~~

### 04-course.success.response.json
대응 스키마: CourseResponse

~~~json
{
  "status": "SUCCESS",
  "course": {
    "id": "33333333-3333-4333-8333-333333333333",
    "profileRevision": 1,
    "createdAt": "2026-11-05T10:00:00+09:00",
    "availableWindow": {
      "startAt": "2026-11-06T13:00:00+09:00",
      "endAt": "2026-11-06T17:00:00+09:00"
    },
    "startAt": "2026-11-06T13:00:00+09:00",
    "endAt": "2026-11-06T15:10:00+09:00",
    "items": [
      {
        "id": "item-01",
        "order": 1,
        "place": {
          "id": "mock-place-001",
          "name": "[가상] 실내 전시공간 A",
          "category": "EXHIBITION",
          "area": "HAEUNDAE",
          "address": "부산광역시 해운대구 — 테스트용 가상 주소",
          "coordinates": {
            "latitude": 35.16,
            "longitude": 129.16
          },
          "indoor": true,
          "openHours": {
            "status": "KNOWN",
            "description": "테스트 설정: 10:00~18:00"
          },
          "price": {
            "status": "UNKNOWN",
            "amount": null,
            "currency": "KRW",
            "basis": "UNKNOWN"
          },
          "defaultStayMinutes": 60,
          "accessibility": {
            "grade": "UNKNOWN",
            "wheelchair": null,
            "stroller": null,
            "elevator": null,
            "accessibleToilet": null,
            "evidence": []
          },
          "sourceIds": [
            "mock-source-01"
          ]
        },
        "startAt": "2026-11-06T13:00:00+09:00",
        "endAt": "2026-11-06T14:00:00+09:00",
        "stayMinutes": 60,
        "reason": "실내 전시공간으로 실내 위주 선호에 부합합니다.",
        "reasonMethod": "TEMPLATE",
        "isAnchor": false
      },
      {
        "id": "item-02",
        "order": 2,
        "place": {
          "id": "mock-place-002",
          "name": "[가상] 카페 B",
          "category": "CAFE",
          "area": "HAEUNDAE",
          "address": "부산광역시 해운대구 — 테스트용 가상 주소",
          "coordinates": {
            "latitude": 35.162,
            "longitude": 129.163
          },
          "indoor": true,
          "openHours": {
            "status": "KNOWN",
            "description": "테스트 설정: 10:00~18:00"
          },
          "price": {
            "status": "UNKNOWN",
            "amount": null,
            "currency": "KRW",
            "basis": "UNKNOWN"
          },
          "defaultStayMinutes": 60,
          "accessibility": {
            "grade": "UNKNOWN",
            "wheelchair": null,
            "stroller": null,
            "elevator": null,
            "accessibleToilet": null,
            "evidence": []
          },
          "sourceIds": [
            "mock-source-01"
          ]
        },
        "startAt": "2026-11-06T14:10:00+09:00",
        "endAt": "2026-11-06T15:10:00+09:00",
        "stayMinutes": 60,
        "reason": "실내에서 쉬어갈 수 있는 카페입니다.",
        "reasonMethod": "TEMPLATE",
        "isAnchor": false
      }
    ],
    "legs": [
      {
        "fromItemId": "item-01",
        "toItemId": "item-02",
        "mode": "WALK",
        "minutes": 10,
        "method": "DISTANCE_ESTIMATE",
        "isEstimate": true
      }
    ],
    "summary": {
      "totalStayMinutes": 120,
      "totalTravelMinutes": 10,
      "totalWaitingMinutes": 0,
      "totalMinutes": 130,
      "estimatedCost": {
        "status": "UNKNOWN",
        "amount": null,
        "currency": "KRW",
        "basis": "UNKNOWN"
      }
    },
    "validation": {
      "status": "PASSED",
      "checkedHardConstraints": [
        "area",
        "timeWindow",
        "excludedCategories"
      ],
      "unverifiedFields": [
        "price",
        "routeAccessibility"
      ],
      "routeAccessibility": "UNVERIFIED"
    },
    "sources": [
      {
        "id": "mock-source-01",
        "provider": "테스트용 가상 기관",
        "datasetName": "API 연결용 가상 장소 데이터",
        "url": "https://example.invalid/busanfit/mock-data",
        "license": "MOCK_ONLY — 실제 공공데이터·이용허락의 증거가 아님",
        "baseDate": "2026-11-01",
        "retrievedAt": "2026-11-05T09:00:00+09:00"
      }
    ]
  },
  "suggestions": [],
  "warnings": [
    {
      "code": "TRAVEL_TIME_ESTIMATED",
      "message": "이동시간은 추정치이며, 실제 보행 경로와 경로 접근성은 확인되지 않았습니다.",
      "placeIds": []
    }
  ],
  "excludedUnknown": {
    "count": 0,
    "fields": []
  },
  "sessionExpiresAt": "2026-11-05T10:30:00+09:00",
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 04-course.insufficient.response.json
대응 스키마: CourseResponse

~~~json
{
  "status": "INSUFFICIENT_PLACES",
  "course": null,
  "suggestions": [
    {
      "id": "suggestion-01",
      "type": "EDIT_PROFILE",
      "label": "방문 시간을 다시 설정하기",
      "field": "timeWindow"
    }
  ],
  "warnings": [
    {
      "code": "INSUFFICIENT_PLACES",
      "message": "현재 조건으로 방문 가능한 장소가 두 곳 미만입니다. 조건을 직접 변경한 뒤 다시 요청해 주세요.",
      "placeIds": []
    }
  ],
  "excludedUnknown": {
    "count": 3,
    "fields": [
      "openHours"
    ]
  },
  "sessionExpiresAt": "2026-11-05T10:30:00+09:00",
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### 05-place.response.json
대응 스키마: PlaceResponse

~~~json
{
  "place": {
    "id": "mock-place-001",
    "name": "[가상] 실내 전시공간 A",
    "category": "EXHIBITION",
    "area": "HAEUNDAE",
    "address": "부산광역시 해운대구 — 테스트용 가상 주소",
    "coordinates": {
      "latitude": 35.16,
      "longitude": 129.16
    },
    "indoor": true,
    "openHours": {
      "status": "KNOWN",
      "description": "테스트 설정: 10:00~18:00"
    },
    "price": {
      "status": "UNKNOWN",
      "amount": null,
      "currency": "KRW",
      "basis": "UNKNOWN"
    },
    "defaultStayMinutes": 60,
    "accessibility": {
      "grade": "UNKNOWN",
      "wheelchair": null,
      "stroller": null,
      "elevator": null,
      "accessibleToilet": null,
      "evidence": []
    },
    "sourceIds": [
      "mock-source-01"
    ]
  },
  "sources": [
    {
      "id": "mock-source-01",
      "provider": "테스트용 가상 기관",
      "datasetName": "API 연결용 가상 장소 데이터",
      "url": "https://example.invalid/busanfit/mock-data",
      "license": "MOCK_ONLY — 실제 공공데이터·이용허락의 증거가 아님",
      "baseDate": "2026-11-01",
      "retrievedAt": "2026-11-05T09:00:00+09:00"
    }
  ],
  "warnings": [],
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-422-unsupported.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "UNSUPPORTED_CONSTRAINT",
    "message": "이 배포 버전에서는 요청한 조건을 처리할 수 없습니다.",
    "retryable": false,
    "details": [
      {
        "field": "mobility",
        "reason": "휠체어 접근성 검증이 아직 지원되지 않습니다. 조건을 제거하거나 일반 코스로 자동 생성하지 않습니다."
      }
    ]
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-409-revision.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "다른 요청에서 조건이 변경되었습니다. 마지막 성공 응답의 조건을 확인해 주세요.",
    "retryable": false,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-410-session.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "세션이 없거나 만료되었습니다. 새 세션을 시작해 주세요.",
    "retryable": false,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-422-incomplete.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "PROFILE_INCOMPLETE",
    "message": "코스를 생성하기 전에 날짜와 시간을 입력해 주세요.",
    "retryable": false,
    "details": [
      {
        "field": "timeWindow",
        "reason": "방문 시간 미입력"
      }
    ]
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-503-ai.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "AI_UNAVAILABLE",
    "message": "조건을 확실하게 해석하지 못했습니다. 조건 카드에서 직접 입력해 주세요.",
    "retryable": true,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-400-request.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "JSON 요청 형식이 올바르지 않습니다.",
    "retryable": false,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-404-place.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "장소를 찾을 수 없습니다.",
    "retryable": false,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-429-limit.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "요청이 많습니다. 잠시 후 다시 시도해 주세요.",
    "retryable": true,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~

### error-500-internal.response.json
대응 스키마: ErrorResponse

~~~json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "요청을 처리하지 못했습니다.",
    "retryable": true,
    "details": []
  },
  "requestId": "22222222-2222-4222-8222-222222222222"
}
~~~
