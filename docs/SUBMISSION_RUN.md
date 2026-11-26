# 제출용 실행 방법 — BusanFit (DEC-031)

정리일: 2026-11-26. 기준: develop(`03803bd`, #87 병합 후). DB는 **v3 `busanfit_v3.sqlite3`(4개 권역 630곳)**, 지원 범위는 **해운대·서면·광안리·남포 4개 권역, 도보(WALK)**다(DEC-028·DEC-032). v1.0 태그 시점에 커밋·DB SHA·검사 결과를 다시 확인한다.

## 1. 제출 압축에 넣을 파일

v1.0 태그 시점의 **소스 전체**와 아래 공유 DB 두 파일, 이 안내를 함께 넣는다. DB는 Git에 올리지 않고 **제출 압축에만** 포함한다(DEC-005·DEC-031). `.env`·API 키·`.venv`·`node_modules`는 넣지 않는다.

```text
busanfit/
  README.md
  .env.example                 환경변수 이름만(값 없음)
  backend/app/                 서버 소스·schema.sql 포함
  backend/requirements-lock.txt
  frontend/                    package.json·package-lock.json 포함 (node_modules 제외)
  config/                      권역 중심(retrieval.json)·승인 가중치·사후면세점 제외/백화점 예외·weather.json
  contracts/
  evaluation/
  docs/SUBMISSION_RUN.md       이 안내
  data/share/busanfit_v3.sqlite3
  data/share/busanfit_v3.txt   SHA-256·권역별 건수·만든 방법
```

이전 DB(`haeundae_sample_v1`·`v2`)는 넣지 않는다. 일부 폴더만 골라 담지 말고 소스 전체를 기준으로 한다(`config/` 파일이 하나라도 빠지면 서버가 시작하지 않는다).

## 2. 실행 환경

| 항목 | 기준 |
|---|---|
| Python | **3.12** (문서 기준). CI는 **3.11·3.12**를 검사한다. 참고: 로컬 Python 3.13.9에서도 `pytest -q`가 통과했으나 제출 기준은 아니다. |
| Node.js | **24** (CI 설정)와 npm |
| DB | SQLite 파일. 별도 DB 서버 없음 |
| 운영체제 | Windows PowerShell 기준. macOS/Linux 명령은 각 절 끝에 짧게 적는다. |

설치 명령은 인터넷에서 패키지를 받는다(PyPI·npm). 실행 중에는 Gemini 키를 넣은 경우에만 외부 API를 호출한다. 이하 명령은 모두 **압축을 푼 저장소 루트**에서 실행한다. 가상환경 활성화는 필요 없다.

## 3. 환경변수

앱은 **`.env`를 자동으로 읽지 않는다.** 서버는 프로세스 환경변수만 본다(`backend/app/ai/gemini.py`의 `os.environ.get`). 예외는 아직 서버에 연결되지 않은 날씨 모듈의 `KMA_SERVICE_KEY` 읽기 함수뿐이다. 이름 목록은 [.env.example](../.env.example)에 있다.

| 이름 | 필수 | 읽는 곳 | 없을 때 |
|---|---|---|---|
| `BUSANFIT_DB_PATH` | **필수** | [backend/app/data/db.py:25](../backend/app/data/db.py#L25) | 서버 시작 실패(기본 경로 없음) |
| `BUSANFIT_WALK_RADIUS_M` | 선택 | [backend/app/data/settings.py:24](../backend/app/data/settings.py#L24) | 1500 m (DEC-001). 숫자가 아니거나 0 이하면 오류 |
| `GEMINI_API_KEY` | 선택 | [backend/app/ai/gemini.py:113](../backend/app/ai/gemini.py#L113) | 규칙 파서로 동작(§6) |
| `GEMINI_MODEL` | 선택 | [backend/app/ai/gemini.py:114](../backend/app/ai/gemini.py#L114) | 키와 **둘 다** 있어야 Gemini 사용 |
| `BUSANFIT_API_TARGET` | 선택 | [frontend/vite.config.js:10](../frontend/vite.config.js#L10) | Vite `/api` 프록시 대상 `http://127.0.0.1:8000` |
| `BUSANFIT_API_PROXY_TARGET` | 선택 | [frontend/vite.config.js:11](../frontend/vite.config.js#L11) | 위 값이 없을 때만 쓰는 예전 이름 |
| `VITE_KAKAO_JS_KEY` | 선택 | [frontend/src/CourseMap.jsx:8](../frontend/src/CourseMap.jsx#L8) | 지도 미표시(타임라인은 표시) |
| `KMA_SERVICE_KEY` | 선택 | [backend/app/weather/settings.py:106](../backend/app/weather/settings.py#L106) (없으면 루트 `.env`도 확인, 같은 파일 :108) | 날씨 모듈만 준비됨. 코스 생성에는 아직 연결되지 않아 서버 실행에 필요 없음(향후 과제, DEC-036) |

수집 파이프라인 전용 `TOURAPI_*` 키는 공유 DB를 쓰면 필요 없다(`pipelines/env.py`).

## 4. 설치 (처음 한 번)

```powershell
python --version                      # 3.12.x 권장 (3.11도 CI 통과)
node --version                        # v24.x
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
npm.cmd --prefix frontend ci
```

macOS/Linux: `python3 -m venv .venv && .venv/bin/python -m pip install -r backend/requirements-lock.txt && npm --prefix frontend ci`

## 5. 백엔드 실행 — 터미널 A

```powershell
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/busanfit_v3.sqlite3).Path
$expected = 'e8bd5c5142af936e819e71036a7919fa0c847a707dceec94d9b5e6a4a219a6fc'
$actual = (Get-FileHash -LiteralPath $env:BUSANFIT_DB_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'DB SHA-256 불일치: busanfit_v3.sqlite3를 다시 받으세요' }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

macOS/Linux:

```bash
export BUSANFIT_DB_PATH="$(pwd)/data/share/busanfit_v3.sqlite3"
sha256sum "$BUSANFIT_DB_PATH"         # macOS: shasum -a 256, 결과가 e8bd5c51…a6fc 이어야 함
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

- v3: 839680바이트, 장소 630곳(해운대 107·서면 258·광안리 64·남포 201). 자세한 건수는 `busanfit_v3.txt`.
- `Application startup complete.`가 나오면 준비된 것이다. API 문서: <http://127.0.0.1:8000/docs>
- 단일 worker로 실행한다. 세션은 메모리에만 있어 서버를 재시작하면 새 대화로 시작한다.
- DB·`config/`·승인 가중치가 없거나 잘못됐거나, 4개 권역 중 하나라도 중심 조회에 실패하면 시작하지 않는다(가상 데이터로 대체하지 않음).

## 6. Gemini 키 (선택)

**키가 있을 때**: 같은 터미널에서 서버를 시작하기 **전에** 두 값을 넣는다. 키는 화면·문서·압축에 남기지 않는다.

```powershell
$env:GEMINI_API_KEY = '<본인 키>'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'   # 팀 검증에 쓴 모델(docs/GEMINI_LIVE_CHECK_2026-11-18.md)
```

또는 키를 넣은 파일을 uvicorn이 읽게 한다(`python-dotenv`가 잠금 목록에 있음): 위 실행 명령 끝에 `--env-file .env`를 붙인다. 앱 코드는 `.env`를 직접 읽지 않는다. macOS/Linux는 `export GEMINI_API_KEY=...`.

**키가 없을 때(기본)**: Gemini를 부르지 않고 **규칙 파서**로 조건을 읽는다. 채팅 응답에 `AI_FALLBACK` 경고가 붙고, 추천 이유는 확인된 장소 정보로 만든 기본 문장이다. 규칙 파서는 아래 형식만 확실히 읽는다.

- 권역 이름: `해운대`·`서면`·`광안리`·`남포` 중 하나
- 날짜 하나: `2026-11-28` / `2026/11/28` / `2026년 11월 28일`
- 시간 범위 `…부터 …까지`: `오전/오후 N시` 또는 24시간 `13:00`. **`1시`~`11시`처럼 오전/오후 없는 시각은 읽지 않는다.** "내일"·"오후쯤" 같은 말은 조건 카드에서 직접 고른다.

키 없이 쓸 입력 예시:

```text
서면, 2026-11-28 오후 1시부터 오후 6시까지
광안리, 2026년 11월 28일 오전 10시부터 오후 3시까지, 휠체어
남포, 2026-11-29 13:00부터 18:00까지, 카페는 빼줘
```

읽지 못한 조건은 질문이나 조건 카드로 다시 묻는다. 방문 날짜는 실행하는 날 이후로 바꿔 쓴다.

## 7. 프론트 실행 — 터미널 B

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

macOS/Linux: `npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173`

- 접속 주소: **<http://127.0.0.1:5173>** (프론트). API는 Vite `/api` 프록시로 `http://127.0.0.1:8000`에 전달된다.
- 다른 API 서버를 쓰면 Vite 시작 전에 `$env:BUSANFIT_API_TARGET = 'http://127.0.0.1:8001'`처럼 설정한다.
- 지도는 `VITE_KAKAO_JS_KEY`(Vite 시작 전 셸에 설정. Vite는 서버와 달리 `frontend/.env`도 스스로 읽는다)와 카카오 앱의 사이트 도메인에 `http://127.0.0.1:5173` 등록이 필요하다. 키가 없으면 지도만 보이지 않고 타임라인·코스는 동작한다. 키는 제공하지 않는다.

## 8. 종료

- 각 터미널에서 **Ctrl+C**. 프론트·백엔드 모두 같다.
- 백그라운드로 띄웠거나 창을 닫아 포트가 남아 있으면 해당 프로세스를 끈다.

```powershell
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.OwningProcess -gt 0 } | ForEach-Object { Stop-Process -Id $_.OwningProcess }
```

macOS/Linux: `kill $(lsof -t -i :8000 -i :5173)`

## 9. 지원 확인과 최소 API 흐름

1. 새 `POST /api/sessions` 응답의 `capabilities.supportedAreas`가 `HAEUNDAE`·`SEOMYEON`·`GWANGALLI`·`NAMPO` 4개, `supportedTransports`가 `WALK`, `supportsUnknownAccessibilityInclusion=true`인지 확인한다.
2. 채팅(`POST /api/chat`) 또는 프로필 전체 PUT으로 지역·시간을 저장한다. PUT 성공 응답의 `status`·`profileRevision`을 쓴다.
3. `READY`일 때만 `POST /api/courses`에 sessionId·최신 profileRevision을 보낸다. 후보 부족(`INSUFFICIENT_PLACES`)도 정상 결과일 수 있다.
4. 정보 없는 장소 포함 칩은 확인창만 연다. 수락하면 최신 프로필에서 `includeUnknownAccessibility`만 true로 바꿔 전체 PUT → 새 revision으로 POST한다. 포함되면 `CONDITIONAL`과 `UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds`를 표시한다.

상세 흐름은 [프론트 연결 안내](ISSUE30_FRONTEND_HANDOFF.md)를 따른다.

## 10. 자동 검사 (외부 API 호출 없음)

`BUSANFIT_DB_PATH`를 설정한 셸에서 실행한다. 결과 파일은 기존 근거를 덮어쓰지 않도록 `*-local.json`으로 저장한다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe contracts/validate_contract.py
.\.venv\Scripts\python.exe contracts/validate_source_sync.py
.\.venv\Scripts\python.exe evaluation/courses/run.py --mode real --runtime-app --travel-provider app.travel.walking:create_travel_provider --expected-db-sha256 e8bd5c5142af936e819e71036a7919fa0c847a707dceec94d9b5e6a4a219a6fc --output evaluation/courses/results/runtime-real-local.json
```

CS-01~10 평가셋은 해운대 사례다. v3의 해운대 107곳은 v2와 같다(`busanfit_v3.txt`). 이전 근거([TEST_EVIDENCE_2026-11-21](TEST_EVIDENCE_2026-11-21.md))는 v1으로 실행한 당시 기록이다. 평가셋의 result·방문일·기대 결과를 통과하도록 바꾸지 않는다. Python `-O`는 감사 assert를 끄므로 쓰지 않는다.

## 11. 문제 확인

| 증상 | 확인할 것 |
|---|---|
| 시작 실패 | 같은 터미널의 `BUSANFIT_DB_PATH`(절대 경로·파일 존재·SHA), `config/` 파일, 의존성 설치 |
| supportedAreas가 4개가 아님 | DB가 v3인지, `app.main:app`으로 실행했는지, 서버 재시작 후 새 세션인지 |
| `AI_FALLBACK`이 계속 뜸 | 키 없이 실행 중이면 정상. 키를 넣었다면 `GEMINI_API_KEY`·`GEMINI_MODEL` 둘 다 **서버 시작 전** 같은 터미널에 설정했는지 |
| 조건을 못 읽음 | §6 형식(날짜 하나, 오전/오후 또는 24시간, 권역 이름) |
| API 연결 실패 | 8000 서버 실행 여부, Vite 프록시 대상(`BUSANFIT_API_TARGET`) |
| PUT 422 / POST 409·410 | 전체 프로필·미지원 조건 / 최신 revision·세션 만료·서버 재시작 |
| 지도 미표시 | `VITE_KAKAO_JS_KEY`와 카카오 앱 도메인(`http://127.0.0.1:5173`) |
| 포트 사용 중 | §8 종료 명령으로 남은 프로세스 정리 |

## 12. 최종 제출 전 확인

v1.0 태그 커밋·DB SHA(`e8bd5c51…a6fc`)·Python/Node 버전·화면 인수 결과를 맞춘다. 데이터 이용조건(공공누리·출처 표시 한국관광공사)은 `busanfit_v3.txt`·[data README](../backend/app/data/README.md) (e)를 따른다. 상시 서버 배포는 하지 않는다.
