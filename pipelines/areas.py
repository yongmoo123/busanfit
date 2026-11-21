"""권역 표 — 파이프라인에서 권역별 값은 여기 한 곳에만 둔다 (FR-020, 이슈 #36 권역 확장).

- 권역 코드: contracts/openapi.json의 area enum과 같은 이름 (HAEUNDAE, SEOMYEON, GWANGALLI, NAMPO).
- 법정동 코드: TourAPI ldongCode2 응답 (부산광역시 lDongRegnCd=26, 시군구 lDongSignguCd).
- 원본 폴더: 해운대는 기존 경로 data/raw/tourapi/ 를 그대로 쓰고(옮기지 않음),
  다른 권역은 data/raw/tourapi/<권역 코드>/ 아래에 같은 구조(list/, common/, intro/, ...)로 둔다.
- 보고용 기준점(report_center): 해운대만 정해져 있다(해운대해수욕장, DEC-023 ①).
  다른 권역은 중심 좌표가 아직 정해지지 않아 None이다. 런타임 중심 좌표는 config/retrieval.json이 기준이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw" / "tourapi"
BUSAN_NAME = "부산광역시"
BUSAN_LDONG_REGN_CD = "26"


@dataclass(frozen=True)
class Area:
    code: str                 # openapi.json area enum
    sigungu_name: str         # ldongCode2 시군구 이름
    ldong_regn_cd: str        # 시도 코드 (부산 26)
    ldong_signgu_cd: str      # 시군구 코드
    raw_subdir: str | None    # RAW_ROOT 아래 폴더. None = RAW_ROOT 자체 (해운대 기존 경로)
    report_center: tuple[float, float] | None = None

    @property
    def raw_dir(self) -> Path:
        return RAW_ROOT if self.raw_subdir is None else RAW_ROOT / self.raw_subdir

    @property
    def default_db(self) -> Path:
        return REPO_ROOT / "data" / f"{self.code.lower()}_sample.sqlite3"


AREAS: dict[str, Area] = {a.code: a for a in (
    Area("HAEUNDAE", "해운대구", BUSAN_LDONG_REGN_CD, "350", None, (35.159084, 129.160279)),
    Area("SEOMYEON", "부산진구", BUSAN_LDONG_REGN_CD, "230", "SEOMYEON"),
    Area("GWANGALLI", "수영구", BUSAN_LDONG_REGN_CD, "500", "GWANGALLI"),
    Area("NAMPO", "중구", BUSAN_LDONG_REGN_CD, "110", "NAMPO"),
)}
DEFAULT_AREA = "HAEUNDAE"
AREA_CODES = tuple(AREAS)


def get(code: str) -> Area:
    try:
        return AREAS[code]
    except KeyError:
        raise ValueError(f"unknown area {code!r}; one of {', '.join(AREA_CODES)}") from None
