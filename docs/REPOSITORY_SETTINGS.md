# 저장소 설정 확인 기록

- 날짜: 2026-11-08
- 관련: 이슈 #8 작업 B, DEC-010 스프린트 1 협업 준비, CONTRIBUTING.md 공동 파일 규칙
- 현재 상태: 사용자 공개 전환 후 main/develop 보호 설정 적용·재조회 검증 완료. CODEOWNERS는 develop 대상 PR의 검토안이며 병합 전이다.

## 최초 확인 상태 (공개 전환 전)

GitHub REST API로 저장소 정보·협업자·브랜치 보호·ruleset을 조회했다.

| 항목 | 확인 결과 |
|---|---|
| 저장소 | yongmoo123/busanfit, 비공개 |
| 김영무 `yongmoo123` | 관리자 및 쓰기 권한 |
| 김세민 `trigo1245` | 쓰기 권한 |
| 이찬용 `cksdyd3786` | 쓰기 권한 |
| 배진호 `Baejinho03` | 쓰기 권한 |
| main/develop 보호 조회 | 각각 HTTP 403, GitHub Pro 또는 공개 저장소가 필요하다는 응답 |
| ruleset 조회 | HTTP 403, 같은 플랜 제약 |
| 병합 후 브랜치 자동 삭제 | 꺼짐. 선택 사항이므로 이번에 변경하지 않음 |
| CODEOWNERS | 작업 시작 시 로컬에 없음. 이번 브랜치에서 초안 작성 |

403은 보호 규칙의 유무를 확인한 결과가 아니다. 현재 플랜에서 조회·활용이 제한된 것으로 기록한다. 설정 변경 요청은 실행하지 않았다. 유료 업그레이드·공개 전환·권한 변경도 하지 않았다.

## CODEOWNERS 초안

- 기준: 이슈 #8에 명시된 실제 계정, CONTRIBUTING.md 공동 파일, docs/COMPONENT_MAP.md 담당 경계.
- backend 기본 담당은 김영무, frontend는 배진호, 데이터·파이프라인은 이찬용, 문서·평가는 김세민.
- data/retrieval/travel은 호출 담당 김영무와 함께, contracts/domain은 API·화면·데이터 담당자가 검토하도록 지정.
- 저장소 공통 파일·CI·CODEOWNERS는 팀원 4명을 지정. AGENTS.md·CLAUDE.md는 PM 검토 대상으로 지정.
- 담당 지정은 수정 권한 제한이나 단독 병합 담당 지정이 아니다.
- 일치하는 마지막 규칙이 적용되므로 하위 경로 규칙이 상위 규칙을 덮어쓴다. 공동 담당자는 같은 줄에 적는다.
- 코드 소유자 지정은 모든 지정자의 승인 강제와 다르다. 작성자 외 승인 1명, 관련 담당자·PM 검토를 각각 확인해야 한다.
- PR 자동 리뷰 요청은 대상 브랜치의 CODEOWNERS 및 GitHub 플랜 지원이 필요하다. develop에만 병합하면 main에도 자동 적용되는 것은 아니다. 실제 기능 동작은 검증하지 않았다.

## 공개 전환 후 적용 결과 (2026-11-08)

사용자가 저장소를 공개로 전환하고 보호 설정 적용을 요청했다. 저장소 public, ruleset 없음, main/develop 기존 보호 없음(404)을 확인한 뒤 REST API로 두 브랜치에 설정을 적용했다. PUT은 각각 200이며 이후 GET 결과로 아래 값을 검증했다.

| 설정 | main | develop |
|---|---|---|
| PR 필수 | 적용 | 적용 |
| 작성자 외 승인 | 최소 1명 | 최소 1명 |
| 필수 CI | checks (3.11), checks (3.12) | checks (3.11), checks (3.12) |
| CI 제공자 | GitHub Actions (app ID 15368) | GitHub Actions (app ID 15368) |
| 관리자에게도 적용 | 예 | 예 |

develop의 실제 검사 이름·GitHub Actions 앱 ID를 확인했다. main 현재 커밋에는 검사 실행 기록이 없으므로 향후 main 대상 PR에서 두 검사가 실행·통과해야 병합할 수 있다. CI workflow는 main/develop 대상 PR에서 두 버전 검사를 실행하도록 정의되어 있다.

최신 base 동기화 강제(strict), 추가 커밋 후 승인 무효화, 코드 소유자 승인 필수는 활성화하지 않았다. CODEOWNERS 자체는 로컬 초안으로 유지한다. 사용자 요청에 따라 PR·push·병합·이슈 댓글 등록은 수행하지 않았다.

## 설정 기준

대상은 main과 develop이며 기존 규칙이 있다면 먼저 대조하고 필요한 항목을 보완한다.

1. 병합 전 PR 필수.
2. 작성자 외 승인 1명 이상 필수.
3. 필수 CI: `checks (3.11)`, `checks (3.12)` 두 항목 모두. 이름은 `.github/workflows/ci.yml` 및 실제 Actions 검사와 맞춘다.
4. 관리자에게도 적용한다. 추가 커밋 후 승인 무효화·최신 base 동기화 강제는 활성화하지 않는다.

공개 전환 후 위 1~3항을 실제 적용했다. 관리자도 보호 대상으로 포함했다. 이후에도 관련 담당자 검토 등 자동 강제하지 않는 팀 협업 기준은 별도로 확인한다.

## 검증과 남은 작업

- 수행: 팀원 4명의 쓰기 권한 확인, 로컬 경로별 소유자 매칭 및 git diff --check 검사.
- 추가 수행: 공개 상태·기존 규칙 확인, 원격 보호 설정, 두 브랜치의 승인 수·관리자 적용·필수 CI 및 앱 ID 재조회 검증.
- 미수행: GitHub CODEOWNERS 오류 API 검사, 자동 리뷰 요청, 기능 코드 테스트. 실행 코드 변경은 없다.
- 남은 작업: develop 대상 PR의 다른 팀원 검토·병합. main에도 CODEOWNERS를 적용하려면 별도 반영이 필요하다.
- 이슈 #8의 불가 사유 댓글은 아직 등록하지 않았다. 이 문서 내용을 사용해 수동으로 공유할 수 있다.

참고: [GitHub CODEOWNERS 안내](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners), [브랜치 보호 REST API](https://docs.github.com/en/rest/branches/branch-protection).

## 2026-11-11 PR #11 리뷰 반영

`test_schema*.py`의 데이터·API 공동 검토 담당을 CODEOWNERS에 추가했습니다. CONTRIBUTING의 플랜 확인 대기 문구를 공개 전환 결과와 구분해 정리했습니다. CODEOWNERS 병합·자동 리뷰 요청 확인은 아직 남아 있습니다. 이번 수정은 원격 보호 설정을 변경하지 않습니다.
