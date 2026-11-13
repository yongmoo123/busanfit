# FR-001~004 / 이슈 #20 구현·검증 기록

작성일: 2026-11-13(KST). 이 기록은 구현 상태이며 PM·담당 외 리뷰나 원격 develop 병합을 대신하지 않는다.

## 기준과 의존성

- 최신 원격 develop `22f1a036c7b1a6749dacdc94e3257cca7c1911a4`를 별도 clone했다.
- 작업 브랜치: `feature/FR-001-chat-extraction`.
- 기존 작업 폴더의 변경은 보존했다. 다음 선행 PR은 **이 로컬 브랜치에만** 병합했다. GitHub에서 승인·병합한 것이 아니다.
  - #13 정책·계약: `54e901bb784a6c4f7c36af29f3b4b06ea3a9472c`
  - #17 AIService·규칙 파서: `01014eaf2e0279d23397db4ef3df641bdabebbf7`
  - #44 PM 평가셋 초안·DEC-022: `55767bd7e2906a89f5ebd05163165d1297fa8b36`
- 기준: AGENTS.md, CONTRIBUTING.md, DEC-006·007·016·019~022, FR-001~004·018, AI-REQ-02·03·04·06, NFR-002·005.

## 구현

- `/api/chat`: 세션·revision·요청 제한 검사 → 추출 → 재검사 → 부분 병합·정책 → 원자 저장. 기존 USER/HARD와 확인 대기를 보존하고 질문은 최대 2개다. 503은 기존 값을 합쳐 지역·시간이 둘 다 없을 때만 반환하며 상태·revision·TTL은 유지한다.
- Gemini Provider: 서버 환경변수의 키·모델로 generateContent REST를 호출한다. 키는 URL에 넣지 않는다. 스키마·시간 의미·HARD 항목·동행 힌트 모순을 검증하고, 각 시도 10초·1회 재시도 후 규칙 파서로 대체한다. 외부 취소는 전파한다.
- 추출 프롬프트는 미언급 필드 null, 장소 추천 금지, 부정 표현·강도·부분 동행 처리와 한국 기준 날짜를 명시한다. 실제 Provider 응답을 그대로 사용자 설명에 복사하지 않는다.
- ChatRuleParser는 기존 보수적 파서에 명시적 실외 제외·카테고리 제외·부상 문법을 보완한다. 해석하지 못한 하드 조건·변경은 확인 대기로 남긴다. 자연어 날짜·복잡한 예산·수정 의도를 완전히 해석하는 파서는 아니다.
- DEC-019·020: 미지원 이동수단은 그 항목만 보류하고, 사용자 명시 수락 전 바꾸지 않는다. 영유아의 유모차 DEFAULT보다 USER 목록이 우선한다. 기존 이동제약·제외 카테고리의 추가 언급은 합친다.
- DEC-022: 가족·아이의 미확인 영유아 여부는 실제 화면에 표시한 질문을 1회로 기록한다. 다음 채팅에서도 답이 없으면 false와 경고를 적용한다. 지역·시간 질문에 밀려 아직 표시하지 않은 동행 질문은 소진하지 않는다. 동행 인원만 모를 때는 질문하지 않고 UNSET을 유지한다.
- 화면은 chat mock을 실제 API 호출로 전환했다. 채팅·카드 저장은 같은 요청 잠금과 최신 revision을 사용한다. NEEDS_INPUT 카드·경고·명시적 도보 수락·503 직접 입력·409/410 새 대화·429 대기 안내를 제공한다. 새 채팅은 이전 세션 종료를 시도한다. 대화·세션·프로필은 브라우저 메모리에만 둔다.
- AI 로그는 목적·횟수·실패 분류·경과 시간만 기록한다. 사용자 원문·프롬프트·응답·키·세션 ID는 기록하지 않는다. 배포 시 프록시/접근 로그는 별도 검수해야 한다.

## 설치·실행

저장소 루트에서 Python 3.12를 사용한다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
```

일반 서버의 지원 배열은 #21·#22 검증 전까지 비어 있다. 이슈 #20에서 코스 지원을 임의로 선언하지 않는다. 일반 서버에서 활성 조건을 보내면 계약대로 422이며 코스 API는 없다.

실제 추출 Provider를 설정하려면 `backend/.env.example`을 `backend/.env`로 복사하고 로컬에서 GEMINI_API_KEY와 현재 사용 가능한 Gemini Flash 모델의 GEMINI_MODEL을 채운다. `.env`는 Git에서 제외된다. 개발 입력은 가상 시나리오만 사용한다.

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --env-file backend/.env --workers 1 --no-access-log
```

화면·부분 병합 검증 전용 데모는 키와 실제 모델을 사용하지 않는다. 가상 capabilities로 조건 입력을 허용하므로 운영 서비스로 사용하지 않는다.

```powershell
.venv/Scripts/python.exe -m uvicorn app.demo:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

다른 터미널에서 프론트를 실행하고 `http://127.0.0.1:5173/`에 접속한다.

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

## 검증

- Python 3.12.14, 프로젝트 lock 의존성. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`을 설정해 `python -m pytest -q` 실행. 최종 결과는 아래 최종 검사 기록을 따른다. Windows 샌드박스에서 비동기 이벤트 루프가 정지해 네트워크 없는 테스트를 제한 밖에서 실행했다.
- 계약 검사: 5 operations·31 schemas·20 examples·15 정책 사례/negative control. 참고 문서 JSON 동기화 통과. 외부 JSON 필드·경로는 변경하지 않았다.
- 프론트 `npm run lint`, `npm run build` 통과. 개발 의존성 설치 시 기존 npm moderate 취약점 4건이 보고됐다. 강제 버전 변경은 하지 않았다.
- 브라우저 실제 UI: 미지원 자차 입력 → NEEDS_INPUT → 명시적 도보 수락 → READY → 카페 제외 추가 후 시간 유지 → 카드에서 실내 선호 저장 확인.
- 새 채팅의 인사말 → 503 직접 입력 안내와 카드 열기, 이후 지역·시간 입력 복구를 확인했다.
- 360px에서 가로 넘침 없음. 기존 CSS의 후순위 sidebar position 덮어쓰기 문제를 수정했다. 데스크톱 1280×900에서도 확인했다.
- 캡처는 전부 로컬 가상 데모다. [데스크톱](evidence/issue20/chat-desktop.jpg), [모바일](evidence/issue20/chat-mobile.jpg), [503 안내](evidence/issue20/chat-503.jpg).

## 평가

PR #44의 **초안 31개**를 그대로 사용한다. 기준 시각은 `2026-11-12T10:00:00+09:00`으로 고정한다. 원본 cases.json의 `result`는 덮어쓰지 않고 별도 결과 파일을 만든다. 추출 결과와 정책 결과를 분리하며 정책은 직접 함수를 호출한 참고 실행이다. HTTP 동작은 pytest와 화면에서 별도로 검증한다. mustNot 자연어 항목은 수동 검토 대상으로 남긴다.

```powershell
.venv/Scripts/python.exe evaluation/extraction/run.py --provider rules --output evaluation/extraction/results/rules-2026-11-13.json
```

규칙 파서 참고 결과: 필드 **234/279 (83.87%)**, 강도 72/73, 필수 누락 질문 필드 일치 사례 1/4, 질문 2개 초과 0건. 자연어 시간 추출 실패로 지역·시간이 둘 다 없어지는 경우에는 DEC-021대로 503이므로, 정상 LLM을 전제한 초안의 NEEDS_INPUT 정답과 다르게 나온다. 강도 수치는 기대 필드의 strength 비교이며 값 자체를 못 뽑은 항목도 별도의 필드 정확도에 실패로 기록한다.

**실제 LLM 정확도는 측정하지 않았다.** 실행 환경에 키·모델 설정이 없었으며, 위 규칙 점수는 AI-REQ-04의 LLM 목표 85% 충족 증거가 아니다. 키 설정 후 다음 명령으로 가상 입력만 실제 모델에 보내 측정할 수 있다. 재실패 후 규칙으로 대체한 사례 수와 실제 모델 측정 여부도 결과에 남긴다.

```powershell
.venv/Scripts/python.exe evaluation/extraction/run.py --provider gemini --output evaluation/extraction/results/gemini.json
```

남은 인계: 실제 모델 연동·정확도 측정, #44 최소 10문장 담당자 교차 검토, #13·#17·#44 및 본 변경 리뷰/원격 병합, #21·#22의 실제 지원 활성화. FR-015 수정 의도 해석과 유료 시연 전환은 범위 밖이다.

## 최종 검사 기록

2026-11-13(KST): **224 passed**, 기존 Starlette/httpx deprecation 경고 1건. 계약·참고 문서 동기화·pip check·git diff --check 통과. 프론트 lint·build 통과. 실제 모델 호출과 원격 CI는 실행하지 않았다. 최종 규칙 참고 결과는 [결과 JSON](../evaluation/extraction/results/rules-2026-11-13.json)에 실행일·코드 revision·수정 상태·평가셋 버전과 함께 보관한다.
