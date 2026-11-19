"""Model selects verified facts; system realizes 1–2 sentences and inserts numbers.

Free-form model prose cannot establish factual entailment. The narrow output schema
therefore accepts only fact keys. No model text, IDs or sources become API facts.
"""
import asyncio
import math
from collections import Counter
from dataclasses import dataclass
from typing import Annotated
from time import monotonic

from pydantic import Field, StrictStr
from starlette.concurrency import run_in_threadpool

from app.ai.service import CourseContext, Purpose
from app.api.course_models import Course, Place, Source
from app.api.session_models import ContractModel
from app.domain.explanation import ExplanationPlace, FactKey
from app.courses.open_hours import covers
from app.places.presentation import place_payload, source_payloads, warning


class ExplanationChoice(ContractModel):
    placeId: StrictStr
    facts: Annotated[list[FactKey], Field(min_length=1, max_length=2)]


class ExplanationOutput(ContractModel):
    items: Annotated[list[ExplanationChoice], Field(max_length=6)]


@dataclass(frozen=True, repr=False)
class ExplanationResult:
    course: Course
    warnings: list


CATEGORY_SENTENCES = {
    'CAFE': '카페에서 쉬어갈 수 있도록 골랐어요.',
    'FOOD': '식사 장소로 이용할 수 있는 음식점이에요.',
    'EXHIBITION': '전시를 둘러볼 수 있는 장소예요.',
    'ATTRACTION': '관광 장소를 둘러보는 일정으로 배치했어요.',
    'PARK': '공원을 둘러보는 일정으로 배치했어요.',
    'SHOPPING': '쇼핑 장소를 둘러보는 일정으로 배치했어요.',
    'OTHER': '등록된 장소 정보를 기준으로 코스에 포함했어요.',
}


def sentences(item):
    result = {'CATEGORY': CATEGORY_SENTENCES[item.place.category],
              'STAY': f'{item.stayMinutes}분 머물도록 일정을 배치했어요.'}
    if item.place.indoor is True:
        result['INDOOR'] = '실내로 등록된 장소예요.'
    elif item.place.indoor is False:
        result['OUTDOOR'] = '실외로 등록된 장소예요.'
    if item.place.accessibility.wheelchair is True:
        result['WHEELCHAIR'] = '장소의 휠체어 이용 가능 항목이 확인돼 있으며, 이동 경로의 접근성은 별도 확인이 필요해요.'
    if item.place.accessibility.stroller is True:
        result['STROLLER'] = '장소의 유모차 이용 가능 항목이 확인돼 있으며, 이동 경로의 접근성은 별도 확인이 필요해요.'
    return result


def verified_records(course, repository):
    ids = tuple(item.place.id for item in course.items)
    if len(set(ids)) != len(ids) or repository.existing_place_ids(ids) != frozenset(ids):
        raise ValueError('course place no longer exists')
    records = []
    source_ids = []
    for item in course.items:
        record = repository.get_place(item.place.id)
        if record is None or record.id != item.place.id or Place.model_validate(place_payload(record)) != item.place:
            raise ValueError('course facts changed')
        if not covers(record, item.startAt, item.endAt)[0]:
            raise ValueError('course opening hours changed')
        source_ids.extend(record.source_ids)
        records.append(record)
    sources = [Source.model_validate(value) for value in source_payloads(repository, source_ids)]
    if sources != course.sources:
        raise ValueError('course source facts changed')
    return records


class ExplanationGenerator:
    def __init__(self, ai, repository, *, total_budget_seconds=12):
        if (isinstance(total_budget_seconds, bool) or not isinstance(total_budget_seconds, (int, float))
                or not math.isfinite(total_budget_seconds) or not 0 < total_budget_seconds <= 12):
            raise ValueError('explanation budget must be in (0, 12] seconds')
        self.ai, self.repository, self.total_budget_seconds = ai, repository, total_budget_seconds

    async def explain(self, course, mobility=(), *, remaining_seconds=12):
        deadline = monotonic() + min(self.total_budget_seconds, max(0, remaining_seconds))
        records = await run_in_threadpool(verified_records, course, self.repository)
        offered = {item.place.id: sentences(item) for item in course.items}
        # Source overview is context only; its free text can never become returned prose.
        context = CourseContext(tuple(item.place.id for item in course.items), tuple(mobility),
            tuple(ExplanationPlace(record.id, record.name, record.category,
                record.overview[:200] if record.overview else None, tuple(offered[record.id])) for record in records))
        budget = max(0, deadline - monotonic())
        output = None
        if budget > 0:
            try:
                async with asyncio.timeout(budget):
                    result = await self.ai.complete(Purpose.EXPLAIN, ExplanationOutput, context=context)
                    output = result.data
            except Exception:
                # Only model-boundary failures fall back. Cancellation still propagates;
                # Repository failures outside this block remain server errors.
                pass
        choices = output.items if output is not None else []
        counts = Counter(choice.placeId for choice in choices)
        selected = {choice.placeId: choice.facts for choice in choices
                    if choice.placeId in offered and counts[choice.placeId] == 1
                    and len(set(choice.facts)) == len(choice.facts)
                    and all(key in offered[choice.placeId] for key in choice.facts)}
        updated = course.model_copy(deep=True)
        fallback_ids = []
        for item in updated.items:
            facts = selected.get(item.place.id)
            if facts:
                item.reason = ' '.join(offered[item.place.id][key] for key in facts)
                item.reasonMethod = 'LLM'
            else:
                item.reason = offered[item.place.id]['CATEGORY']
                item.reasonMethod = 'TEMPLATE'
                fallback_ids.append(item.place.id)
        # A slow explanation must not publish facts deleted/changed in the meantime.
        current_records = await run_in_threadpool(verified_records, updated, self.repository)
        if current_records != records:
            raise ValueError('course records changed during explanation')
        warnings = []
        if fallback_ids:
            warnings.append(warning('AI_FALLBACK', '일부 추천 이유는 확인된 장소 정보로 만든 기본 설명으로 제공해요.', fallback_ids))
        return ExplanationResult(updated, warnings)
