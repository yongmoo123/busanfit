"""Internal JSON AI boundary. Never log prompts, outputs or exceptions."""
import asyncio
import math
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError


class Purpose(str, Enum):
    EXTRACT = 'extract'
    MODIFY = 'modify'
    EXPLAIN = 'explain'


PROMPTS = {
    Purpose.EXTRACT: '조건을 지정 스키마로 추출하세요. 불확실한 값은 추측하지 마세요. 장소를 추천하지 마세요.',
    Purpose.MODIFY: '수정 의도만 지정 스키마로 반환하세요. 원래 조건을 임의로 삭제하지 마세요.',
    Purpose.EXPLAIN: '제공된 장소 사실만 근거로 지정 스키마의 설명을 반환하세요. 장소·가격·시간·출처를 만들지 마세요.',
}


@dataclass(frozen=True, repr=False)
class CourseContext:
    """Category-only health context. No free-text summary or user history."""
    place_ids: tuple[str, ...] = ()
    mobility: tuple[Literal['WHEELCHAIR', 'STROLLER', 'INJURY'], ...] = ()

    def __post_init__(self):
        if not isinstance(self.place_ids, tuple) or not all(isinstance(i, str) for i in self.place_ids):
            raise ValueError('invalid place IDs')
        if not isinstance(self.mobility, tuple) or not all(i in ('WHEELCHAIR', 'STROLLER', 'INJURY') for i in self.mobility):
            raise ValueError('invalid mobility categories')


@dataclass(frozen=True, repr=False)
class AIRequest:
    purpose: Purpose
    system_prompt: str
    output_schema: dict
    user_message: str | None
    context: CourseContext


class Provider(Protocol):
    async def complete(self, request: AIRequest) -> str:
        """Return JSON text; implementations must support cancellation/timeouts."""
        ...


T = TypeVar('T', bound=BaseModel)


@dataclass(frozen=True, repr=False)
class AIResult(Generic[T]):
    data: T | None
    failure: Literal['TIMEOUT', 'INVALID_OUTPUT', 'PROVIDER_FAILURE'] | None
    attempts: int


class AIService:
    def __init__(self, provider: Provider, *, timeout_seconds: float = 10):
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError('timeout must be a positive finite number')
        try:
            timeout = float(timeout_seconds)
        except OverflowError:
            raise ValueError('timeout must be a positive finite number') from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be a positive finite number')
        self._provider = provider
        self._timeout = timeout

    async def complete(self, purpose: Purpose, output_model: type[T], *,
                       user_message: str | None = None,
                       context: CourseContext | None = None) -> AIResult[T]:
        # Validate before contacting a provider. The boundary deliberately has no
        # arbitrary free-text course summary argument.
        if not isinstance(purpose, Purpose):
            raise ValueError('invalid purpose')
        if purpose == Purpose.EXPLAIN and user_message is not None:
            raise ValueError('explanation cannot receive user text')
        if purpose in (Purpose.EXTRACT, Purpose.MODIFY) and not isinstance(user_message, str):
            raise ValueError('user text is required')
        if context is not None and not isinstance(context, CourseContext):
            raise ValueError('invalid context')
        failure = 'PROVIDER_FAILURE'
        invalid_fields: list[str] = []
        for attempt in range(1, 3):
            prompt = PROMPTS[purpose]
            if attempt == 2 and failure == 'INVALID_OUTPUT':
                prompt += ' 이전 응답을 인용하지 말고 지정 JSON 스키마에 맞춰 다시 생성하세요.'
                if invalid_fields:
                    prompt += ' 확인할 필드: ' + ', '.join(invalid_fields)
            request = AIRequest(purpose, prompt, output_model.model_json_schema(),
                                user_message, context or CourseContext())
            try:
                async with asyncio.timeout(self._timeout):
                    raw = await self._provider.complete(request)
                if not isinstance(raw, str):
                    failure = 'INVALID_OUTPUT'
                    continue
                data = output_model.model_validate_json(raw, strict=True)
                return AIResult(data, None, attempt)
            except TimeoutError:
                failure = 'TIMEOUT'
            except ValidationError as error:
                failure = 'INVALID_OUTPUT'
                # Only developer-defined top-level schema names, no raw input,
                # arbitrary extra keys, validation messages or provider output.
                invalid_fields = sorted({str(e['loc'][0]) for e in error.errors(include_input=False)
                    if e['loc'] and e['loc'][0] in output_model.model_fields})
            except Exception:
                # Do not retain/reflect provider error text or request payloads.
                # asyncio.CancelledError is not caught and cancels immediately.
                failure = 'PROVIDER_FAILURE'
        return AIResult(None, failure, 2)
