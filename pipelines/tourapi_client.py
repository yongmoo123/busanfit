"""Minimal TourAPI client on urllib (no extra dependencies).

Sources for endpoint/parameter/field names (checked 2026-11-12): the Swagger definitions embedded in
the 공공데이터포털 pages
- 한국관광공사_국문 관광정보 서비스_GW: https://www.data.go.kr/data/15101578/openapi.do
  (host apis.data.go.kr/B551011/KorService2)
- 한국관광공사_무장애 여행 정보_GW: https://www.data.go.kr/data/15101897/openapi.do
  (host apis.data.go.kr/B551011/KorWithService2)

Key handling:
- The key is put into the URL exactly once, percent-encoded once. A key that already contains
  ``%`` (an "Encoding" key) is decoded once first, so an Encoding key and a Decoding key give the
  same URL and nothing is double-encoded.
- The key never appears in printed URLs, logs or exception messages: use ``mask_url``.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen

KOR_BASE = "https://apis.data.go.kr/B551011/KorService2"
WITH_BASE = "https://apis.data.go.kr/B551011/KorWithService2"
MOBILE_OS = "ETC"
MOBILE_APP = "BusanFit"
TIMEOUT_S = 30

_KEY_IN_QUERY = re.compile(r"(serviceKey=)[^&#]*", re.IGNORECASE)
_XML_TAG = r"<{0}>\s*([^<]*?)\s*</{0}>"


class CallBudgetExceeded(RuntimeError):
    """``max_calls`` reached; nothing more is requested in this run."""


class TourApiError(RuntimeError):
    """Transport failure. The message holds the masked URL only."""


def normalize_key(key: str) -> str:
    """Return the plain (decoded) key. Decodes once if it looks percent-encoded."""
    key = key.strip()
    return unquote(key) if "%" in key else key


def build_url(base: str, operation: str, params: Mapping[str, object], key: str) -> str:
    query = dict(params)
    query.setdefault("MobileOS", MOBILE_OS)
    query.setdefault("MobileApp", MOBILE_APP)
    query.setdefault("_type", "json")
    query["serviceKey"] = normalize_key(key)
    return f"{base}/{operation}?" + urlencode(query, quote_via=quote, safe="")


def mask_url(url: str) -> str:
    return _KEY_IN_QUERY.sub(r"\1***", url)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    url_masked: str

    def result(self) -> tuple[str | None, str | None]:
        """(resultCode, resultMsg) from a JSON or XML body; (None, None) if not found.

        Gateway errors (e.g. an unregistered key) come back as XML or plain text even with
        ``_type=json``, so both shapes are read.
        """
        text = self.body.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            header = (data.get("response") or {}).get("header") or data.get("header") or {}
            if header:
                return header.get("resultCode"), header.get("resultMsg")
        for code_tag, msg_tag in (("resultCode", "resultMsg"), ("returnReasonCode", "returnAuthMsg")):
            code = re.search(_XML_TAG.format(code_tag), text)
            if code:
                msg = re.search(_XML_TAG.format(msg_tag), text)
                return code.group(1), msg.group(1) if msg else None
        return None, text.strip()[:120] or None

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


class TourApiClient:
    def __init__(self, key: str, base: str, *, max_calls: int,
                 opener: Callable[..., object] | None = None):
        if not key:
            raise ValueError("empty TourAPI key")
        self._key = key
        self.base = base
        self.max_calls = max_calls
        self.calls = 0
        self._open = opener if opener is not None else urlopen  # looked up now (tests patch it)

    def __repr__(self) -> str:
        return f"TourApiClient(base={self.base!r}, calls={self.calls}, max_calls={self.max_calls})"

    def url(self, operation: str, params: Mapping[str, object]) -> str:
        return build_url(self.base, operation, params, self._key)

    def get(self, operation: str, params: Mapping[str, object]) -> Response:
        if self.calls >= self.max_calls:
            raise CallBudgetExceeded(f"max_calls={self.max_calls} reached")
        url = self.url(operation, params)
        masked = mask_url(url)
        self.calls += 1
        try:
            with self._open(Request(url, headers={"Accept": "application/json"}),
                            timeout=TIMEOUT_S) as resp:
                return Response(resp.status, resp.read(), masked)
        except HTTPError as error:
            body = error.read() if hasattr(error, "read") else b""
            return Response(error.code, body or b"", masked)
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise TourApiError(f"request failed for {masked}: {type(reason).__name__}") from None
