# 조건 추출 시도별 계측·반복 측정 — FR-002 / NFR-001·002

목적: 기존 19,625ms 기록이 2회 시도의 합계였으므로 첫 시도 지연과 재시도 원인을 분리한다. 이 변경은 계측·가상 실행 준비이며 실제 Gemini 성능 개선이나 측정 완료가 아니다.

## 계측 범위

AIService.complete의 내부 AIResult에 `attempt_metrics` tuple을 추가했다. 기존 3개 인자 호출은 기본 빈 tuple로 호환되며 외부 API JSON은 바꾸지 않는다. 시도별로 다음을 기록한다.

| 항목 | 의미 |
|---|---|
| attempt | 1 또는 2 |
| retry_reason | 첫 시도는 null, 두 번째는 첫 실패의 TIMEOUT / INVALID_OUTPUT / PROVIDER_FAILURE |
| outcome / detail | 성공·실패·취소 및 고정된 원인 분류 |
| provider_ms | Provider.complete 대기부터 반환/실패까지. HTTP 왕복·응답 해석 등을 포함하며 모델 서버 계산 시간만은 아님 |
| validation_ms | 반환 후 Pydantic JSON·업무 검증 등 종료까지 |
| elapsed_ms | 해당 시도의 Provider+검증 소요시간 |

detail은 NONE, TIMEOUT, NON_TEXT_OUTPUT, INVALID_JSON, SCHEMA_VALIDATION, SEMANTIC_VALIDATION, RATE_LIMITED(HTTP 429), UPSTREAM_UNAVAILABLE(5xx), HTTP_ERROR, INVALID_RESPONSE, NETWORK_ERROR, PROVIDER_EXCEPTION, CANCELLED 중 내부 분류다. 원문·모델 응답·키·세션 ID·예외 본문·HTTP 오류 본문은 로그/계측에 넣지 않는다. 종료된 호출의 최종 failure가 null이어도 첫 실패 원인은 보존한다. 호출별 로컬 tuple이므로 동시 요청의 기록을 섞지 않는다.

기존 INFO 집계 로그에 더해 `ai_attempt` INFO 로그를 남긴다. 애플리케이션의 logging 설정이 INFO를 표시해야 보이며, 전역 로그 수준은 이 변경에서 바꾸지 않는다. 기록 항목은 purpose·시도 번호·고정 원인 코드·밀리초 숫자뿐이다. 취소는 기록 후 전파하고 재시도하지 않는다.

**기존 시도당 10초·재시도 최대 1회·실패 시 호출부의 규칙/템플릿 대체 정책은 유지한다.** 시간초과를 5초로 줄이거나 유료/우선 처리로 바꾸지 않는다.

## 안전한 가상 실행

CLI는 네트워크 없는 OfflineProbeProvider만 만든다. `.env`·키를 읽는 코드, configured_provider/load_dotenv 호출, 실제 Provider를 고르는 CLI 옵션이 없다. 새 키·패키지 설치가 필요하지 않다.

```text
# 저장소 루트, 가상 5회
.venv/Scripts/python.exe evaluation/extraction/measure_latency.py --runs 5 --scenario success --output evaluation/extraction/results/latency-offline-5.json
# 실패/재시도/소진을 섞은 가상 10회
.venv/Scripts/python.exe evaluation/extraction/measure_latency.py --runs 10 --scenario mixed --output evaluation/extraction/results/latency-offline-10.json
```

`--runs`는 5~10이며 같은 고정 가상 입력 LAT-01을 순차 반복한다. scenario는 success / invalid-json / schema / semantic / timeout / rate-limit / provider-error / exhausted / mixed다. 가상 timeout·429는 즉시 고정 예외를 주입한다. 실제 10초를 기다리거나 외부 서버 상태를 측정하는 것이 아니다. mixed는 재시도 소진 사례도 포함할 수 있으며, 가상 주입 검증 자체의 CLI 종료 코드 0을 모델 품질 통과로 해석하지 않는다.

출력에는 회차별 총 소요시간·시도별 계측·성공 여부·재시도 원인 집계·첫 시도 성공 수·평균/p50/p90/max·성공하면서 5초 이내인 비율·실행일·커밋·작업 폴더 변경 여부를 기록한다. 입력 문장·추출 프로필·응답 전문은 저장하지 않는다. 실패가 빠르게 끝나도 5초 이내 성공으로 세지 않는다. `fallbackRequired`와 `fallbackExecuted=false`를 구분한다.

CLI 결과는 항상 `syntheticOnly=true`, `providerKind=OFFLINE_FAKE`, `realModelMeasured=false`, `performanceEvidence=false`다. 가상 수치를 NFR-001의 실제 5초 달성 근거로 사용하지 않는다.

## 실제 측정은 후속

`measure(service, runs=5~10)`는 명시적으로 주입된 AIService를 받을 수 있지만 이 함수도 키를 읽거나 Provider를 자동 생성하지 않는다. 추후 사용자가 실제 측정을 승인한 뒤 별도의 실행 진입점에서 이미 준비된 Provider·모델·reference_now를 지정해야 한다. 이번 CLI는 실제 모델 호출 수단을 제공하지 않는다.

이 함수가 측정하는 총 시간은 AI 경계(프롬프트/스키마 준비·Provider·검증·재시도)이며 HTTP 전체·조건 정책·규칙 파서 대체·코스 생성 시간은 포함하지 않는다. 응답의 JSON/업무 유효성 확인과 추출 정확도 평가도 별개다. 실제 기록에는 모델·요금 구간·입력 ID·시도별 원인·5초 이내 성공률을 구분해야 하며, 5~10회는 원인 진단용 소규모 표본이다.

## 검증 기록 (2026-11-20)

- 별도 브랜치 `feature/FR-002-attempt-latency-metrics`, 기준 develop `8f5c83a`. #72의 DB 연결 변경을 포함하지 않는 별도 작업이다.
- 계측·기존 AIService·Gemini MockTransport 경계 검사: **78 passed, 1 warning**.
- 전체 pytest: **1242 passed, 1 warning**. 경고는 기존 Starlette/httpx 경고다.
- 실제 CLI 가상 5회 success: 성공 5, 재시도 0. 가상 10회 mixed: 성공 9, 재시도 8, INVALID_OUTPUT 원인 재시도 5 / TIMEOUT 1 / PROVIDER_FAILURE 2. 소진 1회는 성공/5초 성공에서 제외했다.
- 원인 분류·동시 호출 격리·취소 전파·원문/응답/예외 비노출·키 환경변수 접근 금지·외부 연결 금지·5~10회 제한을 가상 Provider/MockTransport로 검사했다.
- 계약 6 operations·31 schemas·20 examples·15 정책 사례와 참고 문서 JSON 동기화, diff 검사 PASS.
- 실제 API 호출·`.env`/실제 키 파일 읽기·유료 전환·서비스 활성화·병합은 수행하지 않았다. 현재는 로컬 구현 상태다.

## 후속 승인에 따른 실제 5회 측정 (2026-11-20 19:54 KST)

위 가상 검증 이후 사용자가 기존 키로 실제 5회 측정을 명시 승인했다. 가상 CLI는 그대로 유지하고 workspace의 별도 일회성 실행기로 기존 키를 메모리에서만 사용했다. 키·입력/응답 원문·예외 본문을 출력하거나 저장하지 않았으며 유료 전환은 하지 않았다. 과금 구간 자체를 조회하거나 무료 여부를 검증한 것은 아니다.

- 모델: gemini-3.5-flash-lite. 고정 가상 입력 LAT-01을 5회 순차 실행. 실제 API 요청은 총 5회.
- 전부 1차 시도 성공, 재시도 0회. TIMEOUT·429·스키마/업무 검증 실패 없음. 규칙 대체는 실행하지 않음.
- 전체 AI 경계 시간(ms): 7419.453 / 6185.648 / 6337.357 / 7481.654 / 1816.549.
- 시도별 Provider+검증 시간(ms): 7406 / 6187 / 6344 / 7469 / 1812. 전체 시간과 시도 시간은 서로 다른 타이머 분해능으로 수 ms 차이가 있을 수 있다.
- 평균 5848.132ms, 중앙값 6337.357ms, 최근접 순위 p90·최대 7481.654ms. 5초 이내 성공 1/5(20%): 목표 90% 미달. 소규모 고정 입력 표본이며 추출 정확도·전체 HTTP 서비스 인수 결과는 아니다.
- 지연 대부분이 Provider 호출 구간에 있으며 이 구간은 네트워크·응답 해석을 포함한다. 이 결과만으로 무료 등급·모델 추론·네트워크 중 하나를 원인으로 단정하지 않는다.
- 원문 없는 집계/시도별 JSON은 workspace의 `tmp/latency-metrics/live-5-20261120.json`에 보관했다. 앞선 실행기 준비 실패는 실제 API 요청 0회였으며 완료한 5회 외 추가 API 측정은 하지 않았다.

## 유료 전환 없는 코드 개선 (2026-11-20, 추가 실측 전)

- GeminiProvider에 이벤트 루프 범위의 중첩 가능한 session을 추가했다. AIService의 한 호출 안에서 재시도는 같은 HTTPX AsyncClient를 재사용하며, FastAPI lifespan 및 measure의 5~10회 묶음은 요청 간에도 같은 클라이언트를 유지한다. 실제 TCP 연결 재사용 가능 여부는 상대 서버와 연결 상태에 따르며, MockTransport 검사는 클라이언트 수명/구성 재사용을 확인한다.
- 클라이언트는 첫 Provider 호출 때 생성하고 해당 범위 종료 시 닫는다. 초기화 실패는 기존 AI 실패/재시도 경계 안에서 처리하고, 취소·동시 호출·다른 이벤트 루프 재사용을 검증했다. 앱 lifespan을 끄거나 호출마다 별도 실행 루프를 쓰면 요청 사이 풀 재사용 범위가 달라진다.
- 클라이언트 쿠키는 수락하지 않으며 키는 요청 헤더에만 넣고 클라이언트 기본 헤더에 보관하지 않는다. 로그·보고서에는 키를 넣지 않는다.
- 모델별 정적 JSON 스키마를 AIService 내 최대 16개 캐시한다. Provider에는 매번 독립 복사본을 전달해 재시도/다른 요청의 스키마 오염을 막는다. 프롬프트·입력·응답·조건·출처·검증 결과는 캐시하지 않는다. 고정 모델 타입의 schema가 캐시 대상이며 응답 검증은 매번 수행한다.
- 프롬프트·모델·thinking·출력 토큰 제한·정확도 기준·각 10초/1회 재시도·대체 정책은 바꾸지 않았다. 일반 capabilities 활성화·유료 전환·배포도 하지 않았다.
- 오프라인 검사에서 5회 요청/동시 요청이 클라이언트 1개를 공유하고 종료 시 닫힘을 확인했다. 같은 모델의 3회 요청(재시도 포함)에서 schema 생성은 1회였고 요청별 복사본은 분리됐다. 실제 시간 절감 수치나 5초 목표 달성 근거는 아니다.
- 최종 전체 pytest **1252 passed, 1 warning**, 계약 6 operations·31 schemas·20 examples·15 정책 사례 및 문서 동기화·diff 검사 PASS. 실제 Gemini 추가 호출은 하지 않았다.
- 공식 근거: HTTPX [Client 연결 풀](https://www.python-httpx.org/advanced/clients/)·[AsyncClient 수명 관리](https://www.python-httpx.org/async/). 추가 실제 5회 비교는 사용자 확인 후에만 실행한다. 기존 기준 보고서를 덮어쓰지 않도록 새 측정 파일명을 별도로 준비했다.

## 후속 승인에 따른 개선 후 실제 5회 (2026-11-20 20:05 KST)

사용자가 기존 키·동일 모델·동일 가상 입력의 추가 5회 측정을 승인해 실행했다. 실제 API 요청은 5회이며 전부 첫 시도에 JSON/업무 검증 성공, 재시도·429·시간초과·출력 검증 오류는 없었다. 키·원문·응답·예외 본문 저장/출력 및 유료 전환은 하지 않았다.

| 회차 | 전체 AI 경계(ms) | 첫 시도(ms) | 재시도 |
|---|---:|---:|---|
| 1 | 1952.912 | 1937 | 없음 |
| 2 | 1598.317 | 1610 | 없음 |
| 3 | 1578.140 | 1578 | 없음 |
| 4 | 2790.607 | 2781 | 없음 |
| 5 | 2280.983 | 2281 | 없음 |

평균 2040.192ms, 중앙값 1952.912ms, 최근접 순위 p90·최대 2790.607ms. 이번 표본은 5초 이내 성공 **5/5(100%)**로 90% 목표를 충족했다. 이전 평균 5848.132ms·5초 이내 20%와 비교해 평균이 약 65.1% 짧게 관측됐다. 서로 다른 시점의 고정 입력 5회씩 비교이므로 이 차이 전체를 코드 개선의 인과 효과로 단정하지 않으며, 전체 입력/브라우저/API 정확도·공식 NFR 인수 통과를 의미하지 않는다.

워크스페이스 결과: `tmp/latency-metrics/live-5-pooled-20261120-200508.json`, 비교 집계 `tmp/latency-metrics/before-after-20261120.json`. 이전 원본 보고서는 보존했다. 이번 승인된 5회 외 추가 측정은 하지 않았다.

PR 검토용 [전후 측정 집계·시도별 근거](results/latency-live-comparison-2026-11-20.json)는 허용된 메타데이터·시간·고정 실패 분류만 선별했다. 입력/응답 원문·키·실행기 준비 실패의 예외 원문은 포함하지 않는다. 두 실측의 codeRevision은 측정 당시 기준 커밋이고 workingTreeModified=true이며, 최종 구현 커밋으로 측정했다고 바꿔 기록하지 않는다.
