# 배포 구성 예정 영역
SDD 10장·배포 도식은 초안이다. 단일 VM의 Docker Compose에 nginx(React 정적 파일·HTTPS 프록시), API, PostgreSQL+PostGIS, 배치 실행을 둔다.
김영무·이찬용이 기존 공동 배포 역할에 따라 검토하고 프론트 빌드는 배진호와 연결한다. 현재 Dockerfile/Compose/실제 배포는 없다.
SRS 2.3 목표는 Linux/Docker·Python 3.11이며 초기 로컬 검증은 Python 3.12였다. CI에서 둘을 구분해 확인한다.
인메모리 세션은 단일 worker로 시작한다. 프록시 접근 로그의 세션 토큰·건강 원문 보호, 실제 TTL 폐기를 배포 전 검수한다.

세션 경로 보호: [PR #12 세션 로그 검수](SESSION_LOG_PRIVACY.md). Uvicorn의 접근 로그 비활성화만으로 상위 프록시·호스팅 로그 보호를 완료로 간주하지 않는다. 실제 배포 설정은 아직 없으므로 로컬 API 검증과 배포 후 검수를 구분한다.
