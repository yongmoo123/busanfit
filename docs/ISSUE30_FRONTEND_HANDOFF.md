# #30·#31② 실제 API 연결 안내

2026-11-21 #72에서 일반 `app.main:app`의 정보 없는 장소 포함 지원을 활성화했고, #72는 develop에 병합됐다. 백엔드·프론트 모두 **최신 develop**에서 실행한다. 2026-11-26 기준 DB는 v3(4개 권역 630곳), 지원 권역은 해운대·서면·광안리·남포, 이동수단은 도보다. 화면 연결·PC/모바일 인수는 진호 담당이다.

## 실행 준비

설치·Gemini 키·종료 방법은 [제출용 실행 안내](SUBMISSION_RUN.md)를 따른다. 저장소 루트의 PowerShell에서:

```powershell
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/busanfit_v3.sqlite3).Path
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

DB 파일은 커밋하지 않는다. SHA-256은 `e8bd5c5142af936e819e71036a7919fa0c847a707dceec94d9b5e6a4a219a6fc`다. 서버는 `.env`를 자동으로 읽지 않으며, API 키 없이도 규칙 파서·템플릿 경로로 조건 카드·코스를 점검할 수 있다.

프론트는 다른 터미널에서 `npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173`으로 실행하고 브라우저에서 **`http://127.0.0.1:5173`**을 연다. Vite `/api` 프록시 기본 대상은 `http://127.0.0.1:8000`이다. 다른 대상은 Vite 시작 전 `BUSANFIT_API_TARGET`에 실제 접근 가능한 서버 주소를 설정한다.

## 연결 순서

1. 서버 재시작 후 **새 대화/세션**으로 시작하고 `POST /api/sessions` 응답의 `supportsUnknownAccessibilityInclusion=true`, supportedAreas 4개(HAEUNDAE·SEOMYEON·GWANGALLI·NAMPO)와 WALK를 확인한다. 초기 프로필의 동의는 여전히 false다.
2. `INCLUDE_UNKNOWN_ACCESSIBILITY` 칩은 확인창만 연다. 후보 부족(`course=null`)에도 표시하며, 칩 선택만으로 동의를 저장하지 않는다.
3. 명시적 수락 시 **최신 저장 프로필 전체**에서 includeUnknownAccessibility만 true로 바꿔 PUT한다. expectedProfileRevision을 포함하고 다른 value/source/strength를 보존한다.
4. PUT 성공·READY일 때만 **반환된 새 profileRevision**으로 POST /api/courses를 호출한다. POST body는 sessionId/profileRevision만 사용한다. PUT 실패/NEEDS_INPUT이면 POST하지 않는다.
5. 실제 null 장소가 포함되면 CONDITIONAL과 unverifiedFields를 표시한다. UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds를 타임라인 place.id와 연결해 해당 장소에 경고를 표시한다. null을 이용 가능으로 바꾸지 않는다. 확인된 장소만 선택되면 PASSED, 배치할 수 없으면 동의 후에도 INSUFFICIENT_PLACES일 수 있다.

## 실패·동의·표시 점검

- PUT 성공 후 POST만 실패하면 저장된 동의·새 revision을 유지하고 POST만 재시도한다. 이전 revision은 409, 종료 세션은 410을 따른다.
- 저장 전 확인창 취소는 API 요청을 보내지 않는다. 이미 저장된 동의 철회는 최신 revision으로 false 전체 PUT이 성공해야 한다. 창을 닫는 동작만으로 철회됐다고 표시하지 않는다.
- 정규화 후 실제 이동제약 값이 바뀌면 동의가 false로 초기화된다(카드·채팅·영유아 유모차 기본값 포함). 같은 요청의 true보다 초기화가 우선하므로 반환된 프로필·revision으로 별도 재동의한다. 목록 순서·source만 바뀌면 동의를 유지한다.
- 기본값 칩 최대 2개＋포함 칩 1개, 포함 칩이 없으면 기존 기본값 최대 3개다. 후보 부족이면 포함 칩만 반환한다. 이전 코스/처리 중 칩 비활성, PC/360px 모바일·지도·장소별 경고·추천 이유/출처를 점검한다.
- excludedUnknown.count에는 운영시간·주소 등 다른 정보 누락도 포함되므로 전체 수를 접근성 전용 수로 표시하지 않는다.
- 지원 여부는 세션 capabilities를 따른다(날씨 `supportsWeather`는 향후 과제, DEC-036).

## 실제 DB 재현 입력

2026-11-21 해운대·도보(v1 DB로 확인한 당시 기록, v3의 해운대 107곳은 v2와 같음), 이동제약 WHEELCHAIR/STROLLER/INJURY 또는 WHEELCHAIR＋STROLLER:

- 06~08시: 동의 전 후보 부족과 포함 칩 → 동의 후 CONDITIONAL을 확인했다.
- 13~18시: 동의 전 포함 칩, 동의 후 조건부 또는 확인된 장소만 PASSED(부상)일 수 있다.
- 13~14:30: 동의 후에도 시간 부족으로 후보 부족을 유지했다. 성공 코스를 강제하지 않는다.

위 입력은 고정 DB 검증용 조건이다. 실제 연결은 가상 미리보기 응답과 구분해서 확인한다. 서버 검증과 별개로 브라우저·지도·PC/모바일·수동 인수는 아직 미완료다.
