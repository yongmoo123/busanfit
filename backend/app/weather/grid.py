"""위경도 → 기상청 동네예보 격자(nx, ny) 변환 (FR-016).

기상청 단기예보 조회서비스 활용가이드의 Lambert Conformal Conic 변환식(격자 5 km, 표준위도 30°·60°,
기준점 위도 38° 경도 126°, 기준점 위치 x 210 km·y 675 km)을 그대로 옮겼다. 결과는 가이드의 정수 반올림
(``int(x + 1.5)``)과 같다. 확인 값: 서울시청(37.5665, 126.9780) → (60, 127).
"""
from __future__ import annotations

import math

RE_KM = 6371.00877   # 지구 반경
GRID_KM = 5.0        # 격자 간격
SLAT1, SLAT2 = 30.0, 60.0
OLON, OLAT = 126.0, 38.0
XO, YO = 42.0, 135.0  # 기준점 위치 (210 km / 5 km, 675 km / 5 km). 반올림 int(x + 1.5)에서 격자 번호 1 시작을 맞춤


def to_grid(latitude: float, longitude: float) -> tuple[int, int]:
    """(nx, ny). 위경도가 숫자가 아니면 ValueError."""
    if not (isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))) \
            or isinstance(latitude, bool) or isinstance(longitude, bool) \
            or not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError("latitude/longitude must be finite numbers")
    degrad = math.pi / 180.0
    re = RE_KM / GRID_KM
    slat1, slat2 = SLAT1 * degrad, SLAT2 * degrad
    olon, olat = OLON * degrad, OLAT * degrad
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / \
        math.log(math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5))
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5) ** sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + latitude * degrad * 0.5) ** sn
    theta = longitude * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    x = ra * math.sin(theta) + XO
    y = ro - ra * math.cos(theta) + YO
    return int(x + 1.5), int(y + 1.5)
