# 협업 방법

기존 03번 로드맵의 제안 규칙을 작업 시작점으로 옮겼습니다. 저장소 보호 규칙이 실제 설정되었다는 의미는 아닙니다.

## 작업 흐름
1. 최신 develop에서 기능 브랜치를 만듭니다. 예: `feature/FR-001-session`.
2. 이슈에 담당, 요구사항 ID, 선행 입력, 변경 영역, 완료 기준을 씁니다.
3. 작은 단위로 커밋하고 develop을 대상으로 PR을 엽니다.
4. 자동 검사 통과 + 담당 외 팀원 1명 검토 + 문서 갱신 후 병합합니다.
5. main 반영은 검증된 통합본으로 팀이 검토합니다. 초기 빈 저장소 등록 이후에는 이 흐름을 따릅니다.

```text
git switch develop
git pull --ff-only origin develop
git switch -c feature/FR-001-session
```

개인별 장기 브랜치보다 작업 단위 브랜치를 사용합니다. 담당 폴더는 수정 금지 경계가 아니라 리뷰 책임 구분입니다.

## 공동 파일
- contracts 변경: 김영무·배진호 검토, 장소/출처 모델은 이찬용도 검토.
- DB/Repository·이동시간 입출력: 이찬용·김영무 검토.
- 요구사항/완료 기준: 김세민 + 해당 구현 담당 검토.
- 모든 API 변경은 이유·프론트/백엔드 영향·예시·테스트를 함께 갱신합니다.
- 초안 변경을 팀 확정으로 취급하지 않습니다. 합의는 docs/DECISIONS.md에 기록합니다.

## 저장소 관리자 설정
팀원 GitHub 계정으로 Collaborator 초대, main/develop의 PR·리뷰 1명·CI `checks` 필수 규칙을 설정합니다. GitHub 플랜/저장소 설정에 따른 적용 가능 여부를 실제 확인해야 하며, 아직 설정하지 않았습니다.
CODEOWNERS는 팀원 GitHub 계정을 받은 뒤 작성합니다. 이름을 계정명으로 추측하지 않습니다.

## 의존성
requirements.txt와 requirements-dev.txt는 직접 의존성 범위, requirements-lock.txt는 검증한 환경의 전체 고정 버전입니다. 새 가상환경에서 설치·테스트한 뒤 lock을 갱신합니다.
