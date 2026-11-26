"""기상청 공공데이터 API 최소 클라이언트 (urllib, 추가 의존성 없음). FR-016, #33 A단계.

확인(11/24 실제 호출 각 1회, 응답 원본은 저장소 밖에만 보관):
- 단기예보 ``getVilageFcst``: ``response.header.resultCode == "00"``, ``response.body.items.item[]``에
  ``baseDate, baseTime, category, fcstDate, fcstTime, fcstValue, nx, ny``. category 14종
  (TMP UUU VVV VEC WSD SKY PTY POP WAV PCP REH SNO + TMN TMX). PCP·SNO는 "강수없음"·"적설없음" 같은 글자.
- 특보 ``getPwnCd``: 같은 머리부, item에 ``areaCode, areaName, warnVar, warnStress, command, cancel,
  startTime, endTime, allEndTime, tmFc, tmSeq, stnId``(숫자 항목은 JSON 숫자).
- 게이트웨이 오류(키 미등록 등)는 ``dataType=JSON``이어도 XML로 올 수 있어 둘 다 읽는다.

키 처리(pipelines/tourapi_client.py와 같은 규칙): URL에 한 번만, 한 번만 인코딩해 넣는다. ``%``가 있는
(Encoding) 키는 먼저 한 번 디코딩한다. 키는 출력·예외 메시지에 넣지 않는다(``mask_url``).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen

TIMEOUT_S = 10
NO_DATA = "03"   # 해당 자료 없음(특보 없음 등). 오류가 아니다.

_KEY_IN_QUERY = re.compile(r"(serviceKey=)[^&#]*", re.IGNORECASE)
_XML_TAG = r"<{0}>\s*([^<]*?)\s*</{0}>"


class KmaError(RuntimeError):
    """전송 실패·HTTP 오류·결과 코드 오류·형식 오류. 메시지에 키·URL이 없다."""

    def __init__(self, message: str, *, kind: str):
        super().__init__(message)
        self.kind = kind   # "FETCH_FAILED" 또는 "INVALID_RESPONSE"


def mask_url(url: str) -> str:
    return _KEY_IN_QUERY.sub(r"\1***", url)


def build_url(base: str, params: Mapping[str, object], key: str) -> str:
    query = dict(params)
    query.setdefault("dataType", "JSON")
    query["serviceKey"] = unquote(key.strip()) if "%" in key else key.strip()
    return f"{base}?" + urlencode(query, quote_via=quote, safe="")


class KmaClient:
    def __init__(self, key: str, *, opener: Callable[..., object] | None = None, timeout: float = TIMEOUT_S):
        if not key:
            raise ValueError("empty KMA key")
        self._key = key
        self._open = opener if opener is not None else urlopen
        self.timeout = timeout
        self.calls = 0

    def __repr__(self) -> str:
        return f"KmaClient(calls={self.calls})"

    def items(self, base: str, params: Mapping[str, object]) -> list[dict]:
        """한 페이지의 item 목록. 결과 코드 03(자료 없음)은 빈 목록.

        ``numOfRows``만큼 꽉 찼으면 잘렸을 수 있으므로 형식 오류로 본다(일부만 보고 판정하지 않음).
        """
        operation = base.rstrip("/").rsplit("/", 1)[-1]
        url = build_url(base, params, self._key)
        self.calls += 1
        try:
            with self._open(Request(url, headers={"Accept": "application/json"}), timeout=self.timeout) as resp:
                status, body = resp.status, resp.read()
        except HTTPError as error:
            raise KmaError(f"{operation}: HTTP {error.code}", kind="FETCH_FAILED") from None
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise KmaError(f"{operation}: {type(reason).__name__}", kind="FETCH_FAILED") from None
        if status != 200:
            raise KmaError(f"{operation}: HTTP {status}", kind="FETCH_FAILED")
        text = body.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except ValueError:
            code = _xml_code(text)
            raise KmaError(f"{operation}: non-JSON response ({code or 'unknown'})", kind="FETCH_FAILED") from None
        try:
            response = data["response"]
            code = str(response["header"]["resultCode"])
        except (KeyError, TypeError):
            raise KmaError(f"{operation}: no response.header.resultCode", kind="INVALID_RESPONSE") from None
        if code == NO_DATA:
            return []
        if code != "00":
            raise KmaError(f"{operation}: resultCode {code}", kind="FETCH_FAILED")
        try:
            body_obj = response["body"]
            items = body_obj["items"]
            item = items["item"] if isinstance(items, dict) else []
        except (KeyError, TypeError):
            raise KmaError(f"{operation}: no body.items", kind="INVALID_RESPONSE") from None
        if isinstance(item, dict):
            item = [item]
        if not isinstance(item, list) or not all(isinstance(i, dict) for i in item):
            raise KmaError(f"{operation}: items.item is not a list", kind="INVALID_RESPONSE")
        rows = params.get("numOfRows")
        if isinstance(rows, int) and len(item) >= rows:
            raise KmaError(f"{operation}: page full ({len(item)} rows), may be truncated", kind="INVALID_RESPONSE")
        return item


def _xml_code(text: str) -> str | None:
    for tag in ("returnReasonCode", "resultCode", "returnAuthMsg"):
        match = re.search(_XML_TAG.format(tag), text)
        if match:
            return match.group(1)[:60]
    return None
