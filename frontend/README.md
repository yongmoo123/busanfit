# 프론트엔드 — 배진호

담당: 채팅·조건 카드·지도·타임라인·모바일. 관련 FR-001·004~006·011·012·018.
React + Vite 기반 SPA 프로젝트를 생성했습니다. SDD ADR-001에 따라 React를 사용하며, JavaScript와 ESLint를 적용했습니다. 

입력 계약: ../contracts/openapi.json 및 examples. 예시는 전부 가상이며 UI에 가상 표시를 유지합니다.
첫 작업: 채팅/조건 카드/결과 3영역 → READY·NEEDS_INPUT·후보 부족·오류 분기 → 실제 API 연결.
capabilities로 지원 범위를 표시하고 요청을 순차 처리하며 revision을 관리합니다. 민감 데이터는 메모리에만 저장합니다.
지도 연결선은 실제 경로 데이터가 없으면 방문 순서로 표시합니다. 완료 기준은 모바일 360px에서 조건 수정·출처 확인·실패 안내를 재현하는 것입니다.

원본 SRS 6장 UI 목록은 UI-01 채팅, UI-02 조건 카드, UI-03 결과, UI-04 장소 상세·출처, UI-05 편의시설(Should), UI-06 공유(Could)입니다. UI-04까지 첫 흐름에 연결하며 나머지는 우선순위에 맞춰 후속 구현합니다.
SDD ADR-001은 React SPA 기준입니다. 계획서의 Next.js는 대안으로 구분합니다. 김세민은 와이어프레임·검수를 보조합니다.


## 개발 환경

- React + Vite
- JavaScript
- ESLint
- Node.js 24
- npm

## 설치 및 실행

저장소 루트에서 다음 명령어를 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

개발 서버 주소: http://localhost:5173/

## 백엔드 API 프록시

Vite 개발 서버에서 `/api`로 시작하는 요청을
`http://127.0.0.1:8000`으로 전달합니다.

프록시 설정 파일: `vite.config.js`

백엔드 서버가 실행 중이어야 실제 API 요청이 가능합니다.

## 코드 검사 및 빌드

```bash
npm run lint
npm run build
```

## 참고 사항

- `node_modules/`는 Git에 커밋하지 않습니다.
- `package-lock.json`은 Git에 커밋합니다.
- API 계약은 `contracts/openapi.json`을 따릅니다.
- 채팅 UI 및 실제 API 연동은 후속 작업에서 구현합니다.
