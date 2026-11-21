# 테스트 보고서 반영용 검증 근거 — 2026-11-21

대상: 김세민의 [테스트 보고서](test-report.md) 1.3·3.1·3.2·4·6장에 사용할 서버 근거 자료. 기준 소스는 #72 `e2304a9bf624894ba8b4758e9d1fc1c479fcdea1`이며 일반 포함 지원의 실제 평가 실행 코드는 `af9866a85fb5b141a0a03b66895b0a2c52c8f7f9`다. #73 AI 지연 자료는 별도 PR 근거로 분리한다. 이 자료는 최종 v1.0 인수 판정이나 브라우저 통과 보고서가 아니다.

## 1. 보고서에 바로 사용할 요약 문구

> 2026-11-21, 실제 해운대 공유 DB와 직선거리 기반 도보 이동시간 계산기를 일반 서버 시작 경로에 연결했다. 지원되는 CS-01~10 중 9개 시나리오가 자동 검사를 통과했고 실내 HARD 미지원 CS-06 1개는 EXCLUDED로 분리했다. SUCCESS는 8개, 조건상 허용된 INSUFFICIENT_PLACES는 1개였다. 하드 제약 위반과 DB 미존재 장소는 각각 0건이었다. 로컬 TestClient의 코스 POST 9개 모두 15초 이내였고 최대 95.26ms였다. 이는 브라우저·지도·외부 LLM을 포함한 전체 흐름의 성능 인수 결과는 아니다.

> 같은 공유 DB로 휠체어·유모차·부상·복수 이동제약과 3개 시간창을 조합한 포함 제안 검증 12개를 수행했다. 동의 후 7개는 실제 미확인 접근성 장소를 포함한 CONDITIONAL, 1개는 확인된 장소만 포함한 PASSED, 4개는 시간 부족으로 INSUFFICIENT_PLACES를 유지했다. null 보존·장소별 경고·명시적 동의·동의 초기화·POST 재시도와 다른 하드 조건 유지를 확인했다. 일반 서버의 포함 지원은 활성화됐지만, 초기 프로필 동의는 false이며 화면·수동/전체 인수는 미완료다.

자동 회귀는 활성화 수정 후 **1510 passed, 1 warning**(공유 DB 지정, skip 없음), 관련 시작/동의/후보 풀 검사는 **89 passed**였다. 기존 Starlette/httpx 경고 1건이다. pytest 개수는 아래 TC/AC 개수와 다른 지표이므로 합산하지 않는다. 이번 문서 정리에서는 테스트를 재실행하지 않았다.

## 2. 실행·데이터 식별

| 항목 | 확인한 값 / 범위 |
|---|---|
| 서버 Python | 3.12.14, 현재 검증 가상환경에서 확인 |
| CI | Python 3.11·3.12 및 Node24 Frontend lint/build; #72 3개 통과, #73 3개 통과 (11/21 조회) |
| 현재 문서 확인 도구 | Node26.13.0/npm11.20.0; 이전 브라우저 검증 버전으로 사용하지 않음 |
| DB | haeundae_sample_v1.sqlite3, 491520바이트, 읽기 전용 |
| DB SHA-256 | `c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75` |
| 데이터 건수 | places275, open_hours NULL103, accessibility53, data_sources2, 반경1500m 조회107 |
| 무결성 | quick_check=ok, foreign_key_check 위반0, 실제 평가 전후 SHA 동일 |
| 평가셋 SHA-256 | `cdd8d3f75f646707d8bfec65e61af5b894130ef9d47dffafc9011c8fb3213ccb`; 원본 result=null·방문일·기대 결과 미수정 |
| 일반 CS 실행 | `2026-11-21T13:15:50.948165+09:00`, appMode=runtime |
| 포함 지원 실행 | `2026-11-21T13:15:49.178324+09:00`, appMode=runtime, testOnlyApp=false, ordinaryInclusionEnabled=true |
| 실행 코드 | `af9866a85fb5b141a0a03b66895b0a2c52c8f7f9`; 보고서 저장 커밋 e2304a9로 소급하지 않음 |
| 작업 트리 상태 | 원본 보고서 workingTreeModified=true 유지. 결과 파일·미추적 공유 txt 등 작업 상태를 그대로 기록 |
| 반경·중심 | 1500m, 해운대해수욕장 35.159084 / 129.160279 (DEC-023) |
| 계산기 | app.travel.walking:WalkingTravelTimeProvider, 일반4/부상3km/h·우회계수1.0·분 단위 올림·부상 구간당10분 HARD |
| 동행 가중치 | status=APPROVED, pmApproved=true. version 문자열 `draft-2026-11-17`는 과거 라벨이며 승인 상태와 구분 |
| 외부 모델 | 위 #72 검증은 모델 API 요청0. 규칙/템플릿 경로 |
| PR 상태 | #72·#73 리뷰 가능, 두 PR 모두 미병합(11/21 조회) |

출처는 한국관광공사 데이터와 DB의 source 메타데이터를 따른다. 공공누리 유형 등 제출용 이용조건 최종 확인은 데이터 담당 후속으로 남긴다. 해운대 이외 권역·실제 보행 경로를 이 근거에 포함하지 않는다.

## 3. 일반 코스 시나리오 실제 결과

근거: [일반 시작 경로 JSON](../evaluation/courses/results/runtime-real-2026-11-21.json). 모든 시간은 고정 평가셋 입력의 시간창이며 실행일로 자동 치환하지 않았다. CS-08의 정상 후보 부족은 성공 코스 생성과 구분한다.

| 사례 | 자동 판정 | 응답 | POST(ms) |
|---|---|---|---:|
| CS-01 | PASS | SUCCESS | 81.60 |
| CS-02 | PASS | SUCCESS | 66.66 |
| CS-03 | PASS | SUCCESS | 73.96 |
| CS-04 | PASS | SUCCESS | 74.79 |
| CS-05 | PASS | SUCCESS | 63.36 |
| CS-06 | EXCLUDED | 실내 HARD 미지원 | — |
| CS-07 | PASS | SUCCESS | 65.62 |
| CS-08 | PASS | INSUFFICIENT_PLACES | 51.63 |
| CS-09 | PASS | SUCCESS | 95.26 |
| CS-10 | PASS | SUCCESS | 38.15 |

지원 시나리오 분모는 **9개**다. EXCLUDED를 포함해 “10/10 통과”라고 기록하지 않는다. 독립 감사는 장소 ID·반경·운영시간(점유 분 단위)·접근성·시간·출처·이동시간·부상 제한·가격 UNKNOWN을 확인한다. 사후면세점 및 운영시간 NULL 제외도 확인한다. 수동 extraChecks와 전체 인수 플래그는 별도로 남아 있다.

## 4. 포함 제안·동의 후 조건부 코스

근거: [일반 포함 지원 실제 DB JSON](../evaluation/courses/results/unknown-inclusion-runtime-real-2026-11-21.json), [실제 HTTP JSON](../evaluation/courses/results/unknown-inclusion-runtime-http-2026-11-21.json).

| 이동제약 | 시간창 | 동의 전 | 동의 후 / 검증 | 실제 null 장소 수 |
|---|---|---|---|---:|
| WHEELCHAIR | 13:00-18:00 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| WHEELCHAIR | 13:00-14:30 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| WHEELCHAIR | 06:00-08:00 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| STROLLER | 13:00-18:00 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| STROLLER | 13:00-14:30 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| STROLLER | 06:00-08:00 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| INJURY | 13:00-18:00 | SUCCESS | SUCCESS / PASSED | 0 |
| INJURY | 13:00-14:30 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| INJURY | 06:00-08:00 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| WHEELCHAIR+STROLLER | 13:00-18:00 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| WHEELCHAIR+STROLLER | 13:00-14:30 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| WHEELCHAIR+STROLLER | 06:00-08:00 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |

조건부는 접근성 “확인 완료” 판정이 아니다. 별도 풀은 접근성 null만 남은 장소에 거리 근거를 붙이며 주소·시간·반경·확정 제외·접근성 false를 완화하지 않는다. 동의 전에는 null을 넣지 않고, 실제 null이 선택됐을 때만 CONDITIONAL·미확인 필드·장소 ID 경고를 반환한다. null을 true로 바꾸거나 코스 성공을 강제하지 않았다.

실제 임시 Uvicorn HTTP는 06~08시 휠체어 입력에서 후보 부족/포함 칩 → 전체 PUT 동의 → 새 revision POST → CONDITIONAL(미확인 장소 2곳)·상세를 확인했다. 이전 revision409, POST만 재시도, 실제 이동제약 변경 시 동의 false, 세션 삭제도 확인했다. POST 왕복 53.49ms이며 테스트 서버는 종료했다. 이 HTTP 검증도 브라우저 화면 인수와 구분한다.

## 5. 자동 검사·오류 주입 근거

| 근거 | 확인한 내용 |
|---|---|
| [일반 시작 검사](../backend/tests/test_runtime_course_connection.py) | 실제 어댑터 연결·4개 모드·승인 동행/미입력0점·장소 상세·포함 동의·시작 실패·종료 정리 |
| [후보 풀 통합 검사](../backend/tests/test_unknown_retrieval_connection.py) | 31개 회귀: null만 전달·확정 제외·다른 정보 누락 제외·정렬/거리/상한·동의/초기화·조건부 거짓 주장 거절 |
| [포함 정책 검사](../backend/tests/test_unknown_accessibility.py) | 후보 부족 칩·최대2+1·동의 전후·false 제외·카드/채팅/영유아 변경·순서/source 유지·재시도 |
| [독립 감사기](../evaluation/courses/audit.py) | 생산 Validator/운영시간 병합 함수를 호출하지 않는 응답 감사. opt-in 없이 null 허용하지 않음 |
| [계약 검사](../contracts/validate_contract.py) | 6 operations·31 schemas·23 examples·15 정책 사례 및 음성 대조 |
| [참고 JSON 동기화](../contracts/validate_source_sync.py) | 계약·참고 스키마 JSON 일치. 문서 산문/전체 HTTP 동작 검사는 별도 |

검사는 가상 데이터 오류 주입과 실제 공유 DB 평가를 구분한다. 실제 DB에 원하는 false/손상 행을 만들어 검증한 것이 아니다. DB 원본은 변경하지 않았다. CI에는 공유 DB가 없으므로 CI 통과만으로 실제 DB 검증을 대신하지 않는다.

## 6. 보고서 TC/AC/NFR 반영 위치

| 보고서 항목 | 반영 가능한 서버 근거 | 남은 판정 |
|---|---|---|
| TC-007·008·009 | 실제 검색·항목별 접근성·CS 평가/독립 감사 | 사용자 화면과 최종 제출 통합 버전 재확인 |
| TC-013 / AC-006 | 실제 동의→조건부 코스·경고·초기화·재시도 | 휠체어/유모차 브라우저 화면 인수 |
| TC-014 / AC-007 | 기본값 최대2+포함1, 부족 시 포함 칩, 서버 정책 검사 | 화면 표시·FR-015 부분 수정은 별도 미완료 |
| TC-018 | 승인 scorer·동행 미입력0점·기본값 정책 | 화면·시연 및 최종 인수 |
| TC-026·028 / AC-010 | 지원9개에서 미존재0·위반0, 제외1개 구분 | 수동 extraChecks·최종 분모와 통합 결과 확정 |
| AC-011 / NFR-001 코스 | 로컬 POST9/9가15초 이내, 최대 95.26ms | 브라우저·지도·외부 LLM·호스팅 전체 시간 아님 |
| AC-002·012 / NFR-002 | 기존 가상 장애 주입·키 없는 규칙 대체 HTTP 근거 | 브라우저 되묻기·실제 지연 장애 흐름 확인 |
| AC-001·003·005 / NFR-004·007 | API/기본값/상세의 서버 근거만 제공 가능 | 실제 화면·지도·360px·키보드/대비 인수 미실행 |
| AC-008 / FR-010 | 해당 기능 실검증 근거 없음 | 11/25 판단 전 착수하지 않음 |
| AC-009·TC-027·029 | 아래 지연 표본은 추출 정확도 근거가 아님 | 추출 평가셋 정확도·강도·되묻기 평가 별도 |

AC 결과를 일괄 Pass로 채우지 않는다. 특히 AC-004의 엄격 휠체어 코스와 명시적 동의 후 CONDITIONAL 코스를 구분한다. 세민이 담당자별 인수 확인을 받은 후 test-report.md의 최종 결과/판정에 반영한다.

## 7. 별도 #73 Gemini 지연 근거

자료: [PR #73 비교 JSON(고정 커밋 e02a449)](https://github.com/yongmoo123/busanfit/blob/e02a449f2e1ea7dfe12443df07cad5f9d32e4161/evaluation/extraction/results/latency-live-comparison-2026-11-20.json). GitHub의 해당 커밋 자료를 읽어 로컬 기존 근거와 대조했다. #73은 별도 미병합 PR이므로 이 변경이나 수치를 #72 제출본 통합 성능으로 표시하지 않는다.

| 조건 | 실행 시각(KST) | 실요청 | 평균 | 최대 | 5초 이내 성공 | 재시도 |
|---|---|---:|---:|---:|---:|---:|
| 개선 전 | 11/20 19:54 | 5 | 5.848초 | 7.482초 | 1/5(20%) | 0 |
| 개선 후 | 11/20 20:05 | 5 | 2.040초 | 2.791초 | 5/5(100%) | 0 |

모델 gemini-3.5-flash-lite, 같은 고정 가상 입력 LAT-01. 각5회 모두 첫 시도 유효 응답이고 429/타임아웃 없음. 관측 평균은 약65.1% 짧았으나 서로 다른 시점의 소규모 고정 입력 비교다. 정확도85%·전체 사용자 입력·HTTP/브라우저·공식 NFR 인수를 보장하지 않고 감소분 전체를 코드 효과로 단정하지 않는다. 과금 구간 자체는 확인하지 않았고 유료 전환은 하지 않았다. 측정 당시 기준 커밋8f5c83a의 변경 작업 트리였으며 최종 커밋으로 소급하지 않았다. 이번 문서 작업에서 추가 모델 호출은 하지 않았다.

## 8. 아직 채우면 안 되는 결과

브라우저/지도·PC/모바일·수동 extraChecks, 추출/수정 정확도, 새 권역·부분 수정·날씨/고정 일정, 실제 보행 경로·계단/경사, 최종 이용조건·키/로그/접근성 전체 감사, 승인 통합 커밋의 최종 인수는 미확인 또는 별도 일정이다. 기존 결과 JSON의 realDataVerified/realTravelVerified/acceptanceComplete=false는 수동/전체 인수를 자동 완료로 바꾸지 않는 정책으로 보존했다. 실제 DB·실제 계산기를 사용했다는 사실과 최종 검증 완료 여부는 별개다.

## 9. 재현·제출 반영 순서

[제출 실행 안내](SUBMISSION_RUN.md) 7장의 명령으로 로컬 결과를 별도 파일에 저장한다. 최종 제출 통합 커밋·DB/SHA·의존성·실행일을 기록하고, 브라우저 결과를 별도로 추가한다. 이 문서 수치로 원본 cases.json의 result나 최종 AC를 임의로 채우지 않는다. 테스트 보고서 6장의 전체 TC/AC Pass 수·제출 가능 여부는 최종 담당자 확인 후 산출한다.
