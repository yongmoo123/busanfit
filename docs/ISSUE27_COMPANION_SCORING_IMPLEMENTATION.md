# 이슈 #27 — 동행 카테고리 점수화 제안 구현

> 2026-11-19 DEC-029 승인 반영: 11/18 PM이 기존 표와 계수를 승인했다. 설정은 `APPROVED`/`pmApproved=true`이며 파일명·version·가중치 값은 유지한다. 로더는 `PROPOSAL`/false와 `APPROVED`/true만 허용하고 불일치·비 boolean 플래그는 거절한다. 승인 설정은 가상 데모에서 명시적으로 로딩할 수 있다. 일반 서비스는 기존 default_score를 유지하며 실제 데이터 연결(#22·#23) 때 활성화한다. 아래 내용과 검증 수치는 11/17 당시 구현 기록이다.

2026-11-17(KST), 김영무 COMP-03·05 / FR-018, DEC-002·013·020. 가중치는 제안 설정으로 가상 검증하고 PM 확인 전 일반 경로에는 활성화하지 않는 범위입니다.

## 기준과 구현

- 최신 원격 develop `22f1a03`에서 `feature/FR-018-companion-scoring`을 만들고 #26의 `1adf6e5`까지 재사용했습니다. 선행 PR #48·#49·#50·#54·#55가 미병합이면 develop diff에 선행 변경도 포함됩니다.
- `config/companion-weights.proposal.json`: PROPOSAL/pmApproved=false. 5개 동행 유형 × 계약7개 카테고리의 명시적 값과 실내/동행 계수입니다. 가족 우대 방향 외 수치·매핑은 PM 미확정입니다. [제안 표·근거·PM 확인 항목](proposals/issue-27-companion-weights.md).
- `courses/companion_scoring.py`: 설정 로더·깊이 불변인 CompanionProposal·순수 점수 함수 ProposalCompanionScorer/ScoreBreakdown. 누락/추가 유형·카테고리·중복 JSON 키·승인 상태 변경·bool/문자열/음수/NaN/무한대·오버플로를 조용히 보정하지 않고 거절합니다.
- 합산은 설정된 실내 계수 × 기존 default_score + 동행 계수 × 카테고리 값입니다. 기본 제안은2×실내 일치 + 1×동행 값(0~3)입니다. SOFT·알려진 동행만 점수화하며 미입력·혼자·기타는 중립입니다. 인원수·영유아·가격·이름·개요를 점수 근거로 읽지 않습니다.
- 기존 `CourseScheduler(scorer=...)` 주입 지점을 사용합니다. 스케줄러·CourseService·일반 앱·기존 가상 앱·API 모델은 수정하지 않았습니다. 일반 경로는 기존 default_score를 유지하며 새 제안 파일을 읽지 않습니다. 환경변수 활성화 스위치도 추가하지 않았습니다.
- 별도 `app.companion_demo:app`만 미승인 점수를 명시적으로 주입합니다. `baseline_app`은 기존 점수 함수입니다. 둘 다 DB·후보·이동시간·모델이 모두 가상이고 제목에 가상/제안 상태를 표시합니다.
- 하드 필터·독립 검증기·시간창·영업시간·접근성·반경·제외 카테고리·부상 최대10분·경로UNVERIFIED를 그대로 사용합니다. 영유아 유모차 HARD와 USER 선택 우선도 기존 정책입니다. 높은 점수가 위반 장소를 통과시키지 않습니다.

## 검증과 실행

Python3.12, backend/requirements-lock.txt 설치 후 저장소 루트에서 실행합니다.

```text
python -m pytest -q
python contracts/validate_contract.py
python contracts/validate_source_sync.py
git diff --check
python evaluation/companions/run.py --output evaluation/companions/results/synthetic-2026-11-17.json
python -m uvicorn app.companion_demo:app --app-dir backend --port 8003 --no-access-log
python -m uvicorn app.companion_demo:baseline_app --app-dir backend --port 8004 --no-access-log
```

데모에서 세션 생성→시간창13:00~15:15/해운대/동행SOFT 카드 저장→코스 생성 순서로 비교합니다. 제안 앱도 실제 LLM·DB를 사용하지 않습니다. 프론트 변경·캡처·실데이터 인수는 수행하지 않았습니다.

- 신규75개 검사: 제안 점수·실내 합산·입력 불변·중립·하드 동행 미지원 유지, 설정 엄격 검증·깊이 불변·오버플로·일반 경로 미활성.
- 같은 후보에서 연인·가족·친구의 순위/선택 차이, 혼자·기타·미입력 기준선 유지, 입력 후보 순서 무관, #25 설명과 #26 제안 공존을 확인합니다.
- 고득점 장소의 미확인/불가 접근성·영업시간·반경·권역·제외·HARD실내 위반을 거절하며, 부상 구간10분 제한·장소 수 축소/체류 확대와 발견된 계획의 기존 방문 수 우선순위를 확인합니다.
- 독립 하드 검사기·기존 계약과 동행6유형×기준선/제안 총12개 HTTP/ASGI 시나리오를 실행합니다. 결과는 코드revision·실행일·제안파일SHA256·작업트리 상태와 함께 기록하며 세션 ID·사용자 원문은 저장하지 않습니다.
- 실제 데이터 적합성·모델 품질·15초 성능 인수 결과가 아닙니다. 전체 **510 passed**(선행435 + 신규75), 기존 Starlette/httpx 경고1건. 계약5 operations·31 schemas·20 examples·15 정책 사례/negative controls 및 참고 문서 JSON 동기화 통과. 가상 HTTP12개 시나리오는 하드 위반·미존재 ID 0건이며 제안 파일 version/SHA256을 함께 기록합니다.

## 남은 작업

1. 제안 표·수치·카테고리 매핑·실내 대비 계수를 PR에 제시하고 PM 확인 받기. 현재는 미확정이며 일반 경로 비활성입니다.
2. PM 결정 기록 후 별도 활성화 변경 검토. 설정의 pmApproved만 바꿔도 자동 적용되지 않습니다.
3. 실제 #22·DB·이동시간 연결 후 카테고리 분포·동점·후보 편중과 실제 코스 적합성 검증.
4. 분위기·야경·활동성·인원 적합성 근거 데이터 확보 여부와 향후 정책 합의. 가격 UNKNOWN 동안 가성비 점수는 제외합니다.
5. 선행 PR 병합 후 최신 develop 통합 검사. 프론트 표시·실제 LLM·부하/호스팅 검증은 별도입니다. 이번 작업은 로컬 구현·검증이며 PR 게시·PM 승인·이슈 종료를 수행하지 않습니다.


## 기존 PR #56 서버 완료 기준 보완 (2026-11-17)

새 PR 대신 #48→#49→#50→#54→#55의 보완을 전달하고 전체 완료 기준·SQLite/세션 종료 근거 수집을 결합했다. 최종729개 서버 테스트와 계약6 operations를 검증하며 미승인 가중치·일반 경로 비활성 조건은 그대로다. [기존 PR별 증거와 미완료 입력](SERVER_COMPLETION_AUDIT_2026-11-17.md).
