# 프로젝트 문서 — 관리 규칙

담당: 김세민(PM). 이 폴더의 문서는 소프트웨어공학 과제 산출물이며, 코드와 같은 방식(Git·PR·리뷰)으로 관리한다.

## 1. 문서 구성

| 파일 | 종류 | 역할 |
|---|---|---|
| `srs.md` | 기준 문서 | 요구사항의 유일한 기준 (FR·NFR·AI-REQ·UC·AC) |
| `sdd.md` | 기준 문서 | 설계의 유일한 기준 (아키텍처·컴포넌트·DB·API 개요) |
| `plan.md` | 기준 문서 | 프로젝트 계획서 (범위·일정·역할·위험) |
| `../contracts/openapi.json` + `API_CONTRACT.md` | 기준 문서 | API 형식(OpenAPI)과 의미 규칙의 유일한 기준 |
| `DECISIONS.md` | 기록 | 결정 로그. 기준 문서와 다르면 확정 결정이 우선 |
| `meetings/YYYY-MM-DD.md` | 기록 | 회의록 (참석자·안건·결정·할 일) |
| `images/`, `diagrams/` | 자료 | 문서에 들어가는 그림과 그 원본 파일 |

같은 내용을 두 문서에 복사하지 않는다. 다른 문서의 내용이 필요하면 링크한다.
SDD 6장 API 표는 개요만 두고, 필드·상태·오류의 상세는 API 계약을 기준으로 한다.

## 2. 버전 규칙

| 버전 | 시점 | 내용 |
|---|---|---|
| v0.1 | 2026-10-24 | 중간발표 초안 (원본 docx) |
| v0.2 | 스프린트 1 종료 (11/09) | DEC-001~012 반영, 상세 설계 보완 |
| v0.3 | 스프린트 2 종료 (11/23) | 구현 중 바뀐 설계 반영 |
| v1.0 | 최종 (12/14) | 최종 제출본 |

- **버전 번호는 마일스톤에서만 올린다.** 그 사이의 수정은 Git 커밋 이력으로 추적한다.
- 각 문서 상단의 "문서 관리" 표에 버전마다 한 행을 추가한다: 버전·날짜·작성자·주요 변경·관련 결정(DEC-xxx)·관련 PR.
- 마일스톤 시점의 main 커밋에 **저장소 태그**(`v0.2`, `v0.3`, `v1.0`)를 붙인다. 문서와 코드가 같은 태그로 묶이므로 "v0.2 설계서가 기준으로 삼은 코드"를 언제든 꺼내볼 수 있다.
- 태그마다 GitHub Release를 만들고, 제출용 docx/PDF와 그 시점 테스트 결과를 첨부한다.

## 3. 변경 절차

1. 결정이 필요한 변경이면 먼저 `DECISIONS.md`에 기록한다.
2. `docs/<요구사항 ID 또는 DEC ID>-<내용>` 브랜치에서 수정하고 develop으로 PR을 연다. PR 제목에 관련 ID를 쓴다. 예: `docs: DEC-005 SQLite 반영 (SDD)`
3. 리뷰: 요구사항 변경은 PM + 해당 구현 담당, 설계·API 변경은 영향받는 담당자 전원.
4. **코드가 요구사항·설계·API와 달라지는 PR은 해당 문서 수정을 같은 PR에 포함한다.** 문서 수정이 빠지면 리뷰에서 반려한다.
5. 병합 후 `DECISIONS.md`의 "반영 위치" 체크박스를 표시한다.

## 4. ID 규칙

- 요구사항·유스케이스·컴포넌트·결정 ID(FR-, NFR-, AI-REQ-, UC-, COMP-, API-, DEC-)는 **번호를 바꾸거나 재사용하지 않는다.**
- 삭제한 항목은 지우지 않고 `(삭제 — v0.2, DEC-xxx)`로 표시한다. 추적표와 이전 발표 자료가 깨지지 않게 하기 위해서다.
- 새 항목은 마지막 번호 다음을 사용한다.
- 커밋·이슈·PR에는 관련 ID를 쓴다. 이것이 요구사항→설계→코드→테스트 추적성의 근거가 된다.

## 5. 그림

- 다이어그램은 **편집 가능한 원본 파일**(draw.io, PlantUML, Mermaid 등)을 `diagrams/`에, 문서에 넣는 이미지를 `images/`에 둔다. 이미지만 있으면 수정할 수 없기 때문이다.
- 파일명은 문서 그림 번호를 따른다. 예: `diagrams/sdd-5-1-er.drawio` → `images/sdd-5-1-er.png`

## 6. 제출용 변환

원본은 Markdown이고, 제출용 docx는 pandoc으로 만든다. 기존 docx를 서식 기준으로 쓰면 표·제목 스타일이 유지된다.

```text
pandoc docs/sdd.md -f gfm -o build/02_설계서SDD_5팀_부산핏_v0.2.docx --reference-doc=docs/templates/reference.docx --resource-path=docs --lua-filter=docs/templates/br-to-linebreak.lua
```

`br-to-linebreak.lua`는 표 셀 안의 `<br>`을 Word 줄바꿈으로 바꾼다. 이 필터를 빼면 pandoc이 `<br>`을 버려 여러 줄 셀이 한 줄로 붙는다.

생성한 docx/PDF는 저장소에 커밋하지 않고 Release에 첨부한다.

## 7. 최초 이관 (v0.1 → Markdown)

v0.1 docx를 그대로 Markdown으로 바꿔 **먼저 커밋한 뒤** v0.2 수정을 시작한다. 그래야 v0.1→v0.2 변경이 diff로 남는다.

```text
pandoc 01_요구사항명세서SRS_5팀_부산핏.docx -t gfm -o docs/srs.md --extract-media=docs/images/srs
pandoc 02_설계서SDD_5팀_부산핏.docx -t gfm -o docs/sdd.md --extract-media=docs/images/sdd
```

변환 후 표 깨짐과 그림 경로를 확인한다. 원본 v0.1 docx는 `v0.1` Release에 첨부해 보관한다.
`docs/sources/`의 참고 자료는 필요한 내용을 옮긴 뒤 삭제한다(2단계 작업, Git 이력에는 남음).
