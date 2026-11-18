# 이슈 #26 — 기본값 항목 조정 제안 생성

2026-11-17(KST), 김영무 담당 서버 제안 생성. FR-014 ①, FR-005 / DEC-010·018. 사용자의 범위 지정에 따라 체류시간 제안은 제외하고 기존 조건 카드에서 수정 가능한 기본값만 사용합니다. 칩 UI·화면 캡처는 배진호 담당입니다.

## 기준과 변경

- 최신 원격 develop `22f1a03`에서 `feature/FR-014-default-suggestions`를 만들고 #25의 `533475c`까지 기존 구현을 재사용했습니다. 선행 PR #48·#49·#50·#54 미병합 시 develop diff에 선행 변경도 포함됩니다.
- `application/suggestions.py`의 `build_default_suggestions(profile, capabilities)`는 검증된 최종 적용 프로필만 읽는 순수 함수입니다. LLM·DB·세션·시각·외부 호출에 의존하지 않습니다.
- `source=DEFAULT`이고 value가 null이 아니며 capabilities에서 지원하는 기존 카드 필드만 대상으로 합니다. area/transport는 지원 값 목록도 확인합니다. USER·UNSET·미지원 항목은 제외합니다. 명시적 DEFAULT 빈 목록은 미입력 null과 다르며 값이 있는 것으로 취급합니다.
- 기존 카드 순서(area→transport→timeWindow→mobility→budget→companions→indoorPreference→excludedCategories→preferenceTags)로 최대 3개를 반환합니다. 이는 동일 결과를 위한 표시 순서이며 추천 점수 가중치 정책이 아닙니다. 현재 서버가 실제 자동 적용하는 프로필 기본값은 도보와 영유아 동반 시 유모차입니다. 다른 필드의 기본값을 새로 만들거나 지원 범위를 열지 않습니다.
- 기존 Suggestion의 id/type/label/field만 사용합니다. type은 EDIT_PROFILE, id는 `edit-default-{field}`로 안정적이며 필드별 한 개만 반환합니다. 문구에는 사용자 값·세션 ID·건강 원문을 삽입하지 않습니다.
- CourseService가 도보 기본값·유모차 정규화 후 실제 코스에 사용한 프로필에서 제안을 만듭니다. 오래된 세션 값으로 제안 대상을 추측하지 않습니다. CourseResult 내부 suggestions를 API에 전달하고 외부 필드를 추가하지 않습니다.
- SUCCESS에서만 제안을 붙이며 INSUFFICIENT_PLACES는 suggestions=[]입니다. 실패 응답은 기존 오류 계약을 유지합니다. 제안 생성은 프로필·HARD·revision·코스·검증 결과를 바꾸지 않고, 코스 API의 기존 성공 시 TTL 갱신 규칙을 따릅니다.

## 수정·재생성 의미

칩 선택은 field에 해당하는 카드를 여는 동작입니다. 자동 저장·자동 조건 해제·자동 코스 수정은 없습니다. 사용자가 카드에서 직접 선택한 항목은 source=USER로 저장하고 성공 응답의 최신 profileRevision으로 다시 POST courses를 요청해야 합니다. 이전 revision은409입니다.

같은 도보/유모차 값을 직접 확인해 USER로 저장해도 해당 제안은 사라집니다. 반대로 DEFAULT 값을 그대로 재전송하거나 카드를 열고 닫기만 하면 제안은 유지됩니다. 제안 클릭 이력·일회성 숨김을 저장하지 않으며 최신 코스 성공 응답마다 현재 기본값을 판정합니다. 소비자는 최신 응답으로 칩을 교체하고 이전 응답과 누적하지 않습니다.

유모차는 현재 HARD 기본값을 확인·직접 수정하도록 안내할 뿐입니다. 사용자가 명시적으로 USER/[]로 해제하면 기존 DEC-020 정책을 따르며 다시 자동 적용하지 않습니다. 정보 없음 포함·날씨 제안(#31), 부분 수정(#32), 체류시간 편집 필드와 UI는 범위 밖입니다.

## 검증과 재현

Python 3.12, backend/requirements-lock.txt 설치 후 저장소 루트에서 실행합니다.

```text
python -m pytest -q
python contracts/validate_contract.py
python contracts/validate_source_sync.py
git diff --check
python evaluation/suggestions/run.py --output evaluation/suggestions/results/synthetic-2026-11-17.json
python -m uvicorn app.explanation_demo:app --app-dir backend --port 8003 --no-access-log
```

가상 앱에서 POST sessions → READY 프로필 PUT → POST courses로 suggestions를 확인하고, 해당 field를 USER로 수정한 전체 프로필을 PUT한 뒤 새 revision으로 재생성합니다. 앱은 명시적인 가상 DB·후보·이동시간·모델만 사용합니다. 일반 앱 capabilities는 여전히 실제 연결 검증 전 닫혀 있습니다.

- 신규 테스트 44개: 기존 카드 필드별 DEFAULT/지원 범위, USER·UNSET 제외, 최대3개·중복 제거·표시 순서·안정 ID·입력 불변, 문구에 원문/체류시간/날씨 동작 미포함.
- HTTP: 도보/유모차 제안, USER 확인·저장→revision 증가→재생성 시 제거, 유모차 USER 해제 보존, 동일 DEFAULT 유지, 미지원 CAR 저장422, 생성 시 추가된 기본값, 미완성/후보 부족, #25 설명 성공/실패 대체와 공존 검사.
- 독립 하드 검사기·계약 검사와 함께 가상 HTTP/ASGI 4개 흐름(도보 확인·유모차 확인·유모차 해제·후보 부족)을 실행합니다. 결과는 revision·실행일·작업 트리 상태를 별도 JSON에 기록하며 세션 ID·원문은 기록하지 않습니다.
- 실제 DB·LLM 호출·성능 인수·프론트 클릭/캡처를 검증한 것은 아닙니다. 전체 pytest **435 passed**(선행 391 + 신규 44), 기존 Starlette/httpx 경고 1건. 계약 5 operations·31 schemas·20 examples·15 정책 사례/negative controls, 참고 문서 JSON 동기화와 diff 검사를 통과했습니다.

## 남은 작업

1. 배진호: EDIT_PROFILE 칩을 label로 표시하고 field로 기존 카드 항목 열기/포커스. 클릭만으로 값을 바꾸지 않기. 저장 성공 후 새 revision으로 재생성하고 새 suggestions로 교체하기.
2. 칩→카드→저장→재생성의 실제 프론트 연결·모바일 동작·화면 캡처. 이번 변경은 프론트 코드와 지원 범위를 변경하지 않습니다.
3. #22·실제 DB·이동시간·LLM 및 선행 PR 병합 후 develop 통합 검증. 현재 검증은 가상 포트 기준입니다.
4. #27 점수화, 체류시간 계약 확장, #31 정보 없음/날씨 제안, #32 부분 수정은 별도입니다. 이번 범위를 완료했다고 #26의 UI 완료 기준까지 종료하지 않습니다.
