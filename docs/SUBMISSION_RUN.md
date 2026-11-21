# 제출용 실행 방법 초안 — BusanFit

정리일: 2026-11-21. 실행 근거 소스: PR #72의 `e2304a9bf624894ba8b4758e9d1fc1c479fcdea1`. 이 문서는 해당 구현을 실행하는 안내이며 v1.0 제출 확정본은 아니다. 최종 제출 시 승인된 통합 커밋·#73 반영 여부와 진호의 실제 화면 연결·인수 결과를 다시 확인한다. #73 AI 계측·연결 재사용 변경은 이 구현에 포함되지 않았다.

## 1. 제출 압축에 넣을 파일

소스 폴더와 아래 공유 DB 두 파일, 이 실행 안내를 함께 전달한다. DB는 Git에 올리지 않고 **제출 압축에만** 포함한다. 실제 키나 `.env`, `.venv`, `node_modules`는 압축에 넣지 않는다. 의존성은 고정 목록으로 설치한다.

```text
busanfit/
  README.md
  backend/app/                 서버 소스·schema.sql 포함
  backend/requirements-lock.txt
  frontend/                    package.json·package-lock.json 포함
  config/                      승인 가중치·검색 제외 목록 포함
  contracts/
  evaluation/
  docs/SUBMISSION_RUN.md        이 안내
  docs/TEST_EVIDENCE_2026-11-21.md
  data/share/haeundae_sample_v1.sqlite3
  data/share/haeundae_sample_v1.txt
```

최종 압축은 위 일부만 따로 골라 구성하기보다 해당 통합 커밋의 소스 전체를 기준으로 준비한다. `config/`의 사후면세점 제외 파일·승인 가중치, DB 스키마·참고 JSON이 빠지지 않아야 한다. 이번 정리에서는 압축 제작·배포·제출을 수행하지 않았다.

## 2. 실행 환경

- Windows PowerShell, Python 3.12. 현재 서버 검증 가상환경은 **Python 3.12.14**다. CI는 Python 3.11·3.12를 검사한다.
- 프론트 기준은 Node.js 24(CI 설정)·npm이다. 이번 문서 확인 PC의 설치 도구는 Node.js 26.13.0/npm 11.20.0이며, 이를 이전 브라우저 검증 환경으로 소급하지 않는다.
- DB는 SQLite 파일로 제공하며 별도 DB 서버가 필요 없다.
- 설치 명령은 인터넷에서 패키지를 받는다. 이번 문서 정리에서 신규 가상환경 설치나 패키지 재설치는 수행하지 않았다.

이하 명령은 **소스 폴더의 저장소 루트**에서 실행한다. 경로에 공백이 있으면 PowerShell의 따옴표로 감싼다. Python 가상환경 활성화는 필요 없다.

## 3. DB 파일 확인

```powershell
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/haeundae_sample_v1.sqlite3).Path
$busanfitExpectedSha = 'c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75'
$busanfitActualSha = (Get-FileHash -LiteralPath $env:BUSANFIT_DB_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
if ($busanfitActualSha -ne $busanfitExpectedSha) { throw '공유 DB SHA-256 불일치' }
```

v1 기준 491520바이트, 장소 275곳·운영시간 NULL 103곳·무장애 53행·출처 2행이다. 해운대해수욕장(35.159084, 129.160279) 반경 1500m 조회는 107곳이며, 코스 후보 수는 영업시간·접근성·사후면세점 제외 등에 따라 더 줄어든다. 공유 DB를 쓸 때 빈 DB 생성·재수집·재적재는 필요 없다.

## 4. 백엔드 설치·실행 — 터미널 A

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/haeundae_sample_v1.sqlite3).Path
$env:BUSANFIT_WALK_RADIUS_M = '1500'
$env:GEMINI_API_KEY = $null
$env:GEMINI_MODEL = $null
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

위 기본 재현은 모델 키 없이 **규칙 파서·템플릿 경로**로 실행한다. 실제 Gemini 사용은 별도 승인된 환경의 GEMINI_API_KEY·GEMINI_MODEL을 설정한 경우다. `.env`는 앱이 자동으로 읽지 않는다. 이번 정리에서 실제 키를 조회하거나 추가 모델 호출을 하지 않았다.

이미 `.venv`가 준비되어 있으면 새로 만들거나 재설치할 필요 없다. 현재 영무의 별도 #72 작업 폴더에서는 `.venv` 대신 `../busanfit/.venv/Scripts/python.exe`를 사용했다. 제출본에서는 위처럼 압축을 푼 폴더에 새 가상환경을 만든다.

API 문서: `http://127.0.0.1:8000/docs`. 단일 worker로 실행하며 종료는 Ctrl+C다. 서버 재시작 시 메모리 세션이 사라지므로 새 대화로 시작한다. DB·설정·승인 가중치가 없거나 잘못됐으면 시작에 실패하며 가상 데이터로 대체하지 않는다.

## 5. 프론트 설치·실행 — 터미널 B

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

브라우저에서 `http://127.0.0.1:5173`을 연다. Vite의 `/api` 프록시 기본 대상은 `http://127.0.0.1:8000`이다. 다른 API 서버를 쓰면 프론트를 시작하기 전에 `BUSANFIT_API_TARGET`을 실제 접근 가능한 서버 주소로 설정한다. 프록시 설정은 [vite.config.js](../frontend/vite.config.js)를 따른다.

지도는 `VITE_KAKAO_JS_KEY`와 해당 앱의 도메인 설정이 필요하다. 위 키 없는 기본 명령만으로 지도 표시까지 검증됐다고 판단하지 않는다. 실제 키는 제공하지 않으며, 지도·PC/모바일·포함 버튼의 실제 API 연결은 진호의 후속 검증 대상이다. 가상 미리보기 화면을 실제 서버 인수 결과로 쓰지 않는다.

Linux/macOS에서는 `.venv/Scripts/python.exe`를 `.venv/bin/python`으로, `npm.cmd`를 `npm`으로 바꾸고 셸 방식으로 DB 절대 경로를 설정한다. 이 운영체제의 신규 설치는 이번 정리에서 검증하지 않았다.

## 6. 지원 확인과 최소 API 흐름

1. 새 `POST /api/sessions` 응답에서 HAEUNDAE/WALK와 `supportsUnknownAccessibilityInclusion=true`를 확인한다.
2. 최신 프로필 전체 PUT으로 지역·시간·이동제약을 저장한다. 직접 바꾼 조건의 source는 USER, 서버가 적용한 DEFAULT는 반환값을 보존한다. PUT 성공 응답의 status·profileRevision을 사용한다.
3. READY일 때만 `POST /api/courses`에 sessionId·최신 profileRevision을 보낸다. 후보 부족은 정상적인 결과일 수 있다.
4. 포함 칩은 확인창만 연다. 수락 후 최신 저장 프로필에서 includeUnknownAccessibility만 true로 바꿔 전체 PUT → READY의 새 revision으로 POST한다.
5. 실제 미확인 접근성 장소를 포함한 경우 CONDITIONAL과 `UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds`를 표시한다. 해당 ID는 타임라인의 place.id와 연결하며 null을 이용 가능으로 바꾸지 않는다.

일반 코스·실제 DB 검증과 서버 API 활성화는 완료했지만, 최종 사용자 화면 인수는 남아 있다. 상세 흐름과 고정 DB 검증 입력은 [프론트 인계](ISSUE30_FRONTEND_HANDOFF.md)를 따른다.

## 7. 자동 검사·실제 DB 재현

DB 경로를 설정한 셸에서 실행한다. 아래 검사는 새 Gemini/TourAPI 호출 없이 로컬 DB·규칙 엔진을 사용한다. 실제 공유 DB는 읽기 전용이며 출력 파일은 원본 DB·평가셋과 다른 경로로 지정한다. 기존 제출 근거를 덮어쓰지 않도록 `*-local.json`으로 저장한다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe contracts/validate_contract.py
.\.venv\Scripts\python.exe contracts/validate_source_sync.py
.\.venv\Scripts\python.exe evaluation/courses/run.py --mode real --runtime-app --travel-provider app.travel.walking:create_travel_provider --expected-db-sha256 c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75 --output evaluation/courses/results/runtime-real-local.json
.\.venv\Scripts\python.exe evaluation/courses/unknown_inclusion.py --runtime-app --expected-db-sha256 c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75 --output evaluation/courses/results/unknown-inclusion-runtime-local.json
```

실행 결과는 [테스트 보고서용 근거](TEST_EVIDENCE_2026-11-21.md)와 비교한다. pytest 수는 향후 코드/DB/브랜치 변경에 따라 달라질 수 있다. 원본 cases.json의 result·방문일·기대 결과를 통과하도록 바꾸지 않는다. CLI는 서버 포트를 열지 않고 TestClient로 API를 실행한다. Python `-O`는 감사 assert를 끄므로 사용하지 않는다.

## 8. 문제 확인

| 증상 | 확인할 것 |
|---|---|
| 시작 실패 | 같은 터미널의 BUSANFIT_DB_PATH 절대 경로·파일 존재·SHA, config 파일, Python 의존성 |
| capability가 비어 있거나 포함 false | 실행 코드가 #72인지, `app.main:app`인지, 서버 재시작·새 세션 여부 |
| API 연결 실패 | API 8000 실행 여부와 Vite /api 프록시 대상 |
| PUT 422 | 전체 프로필·source/strength, 미지원 조건, 동의 초기화 정책 |
| POST 409/410 | 최신 revision인지, 세션 만료/서버 재시작 여부. 기존 세션을 무조건 재사용하지 않기 |
| 동의 후에도 후보 부족 | 영업시간·거리·실제 이동시간·부상 제한은 완화하지 않으므로 가능한 정상 결과 |
| 지도 미표시 | 카카오 JS 키·앱 도메인 설정 및 화면 오류 안내. 타임라인은 별도로 점검 |

## 9. 최종 제출 전 확인

확정 통합 커밋·DB/SHA·Python/Node 버전·화면 인수 결과를 맞추고, 제출 압축에만 DB·해시 안내를 동봉한다. #73 AI 개선은 별도 리뷰 중이므로 통합 전 성능을 제출본 전체 성능으로 기록하지 않는다. 데이터 출처/이용조건 및 공공누리 유형은 데이터 담당 최종 확인을 반영한다. 이 안내는 소스 로컬 실행 기준이며 상시 서버 배포는 수행하지 않았다.
