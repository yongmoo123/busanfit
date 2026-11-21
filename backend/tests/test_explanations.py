"""Bounded model selections cannot invent API facts or accept unknown place IDs."""
import asyncio
from dataclasses import replace
import json
import pytest
from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService
from app.application.course_service import CourseService
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.api.profile_models import Profile
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.explanations.generator import ExplanationGenerator
from test_courses import ready


@pytest.fixture
def example():
    places = [synthetic_place(index) for index in range(1, 4)]
    repo = FakeRepository(places)
    caps = build_profile_capabilities(ProfileSupport(candidate_search_connected=True,
        verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True))
    course = CourseService(FakeRetriever(places), FakeTravel(), repo).generate(Profile.model_validate(ready()), 1, caps).course
    return repo, course


def output(course, facts=('INDOOR', 'STAY')):
    return json.dumps({'items': [{'placeId': item.place.id, 'facts': list(facts)} for item in course.items]})


def explain(example, replies, **kwargs):
    repo, course = example
    provider = FakeProvider(replies)
    generator = ExplanationGenerator(AIService(provider, timeout_seconds=0.01), repo, **kwargs)
    return asyncio.run(generator.explain(course)), provider


def test_valid_selection_changes_only_reasons_and_preserves_course(example):
    before = example[1].model_dump(mode='json')
    result, provider = explain(example, [FakeReply(output(example[1]))])
    assert provider.calls == 1 and result.warnings == []
    after = result.course.model_dump(mode='json')
    for old, new in zip(before['items'], after['items']):
        assert new['reasonMethod'] == 'LLM'
        assert new['reason'] == f"실내로 등록된 장소예요. {new['stayMinutes']}분 머물도록 일정을 배치했어요."
        new['reason'], new['reasonMethod'] = old['reason'], old['reasonMethod']
    assert after == before
    assert example[1].model_dump(mode='json') == before


@pytest.mark.parametrize('text', ['bad-json', '{"items":[{"placeId":"synthetic:1","facts":["FREE_PRICE"]}]}',
    '{"items":[{"placeId":"synthetic:1","facts":["STAY"],"reason":"무료 0원"}]}',
    '{"items":[{"placeId":"synthetic:1","facts":[]}]}',
    '{"items":[{"placeId":"synthetic:1","facts":["STAY","INDOOR","CATEGORY"]}]}'])
def test_malformed_or_free_form_prose_retries_then_falls_back(example, text):
    result, provider = explain(example, [FakeReply(text), FakeReply(text)])
    assert provider.calls == 2
    assert all(i.reasonMethod == 'TEMPLATE' for i in result.course.items)
    assert '무료' not in str(result.course.model_dump())
    assert result.warnings[0]['code'] == 'AI_FALLBACK'


@pytest.mark.parametrize('kind', ['unknown-id', 'missing', 'duplicate-id', 'duplicate-fact', 'unsupported-fact'])
def test_invalid_selection_is_discarded_without_removing_verified_course(example, kind):
    repo, course = example
    items = json.loads(output(course))['items']
    first = items[0]['placeId']
    if kind == 'unknown-id': items[0]['placeId'] = 'invented:999'
    if kind == 'missing': items.pop(0)
    if kind == 'duplicate-id': items[1]['placeId'] = first
    if kind == 'duplicate-fact': items[0]['facts'] = ['STAY', 'STAY']
    if kind == 'unsupported-fact': items[0]['facts'] = ['OUTDOOR']
    result, _ = explain(example, [FakeReply(json.dumps({'items': items}))])
    assert result.course.items[0].reasonMethod == 'TEMPLATE'
    assert len(result.course.items) == len(course.items)
    assert all(item.place.id in repo.places for item in result.course.items)
    assert 'invented:999' not in str(result.course.model_dump()) + str(result.warnings)


def test_schema_error_can_recover_with_single_retry(example):
    result, provider = explain(example, [FakeReply('bad'), FakeReply(output(example[1]))])
    assert provider.calls == 2 and all(i.reasonMethod == 'LLM' for i in result.course.items)


def test_two_timeouts_cancel_and_fall_back(example):
    result, provider = explain(example, [FakeReply(delay_seconds=1), FakeReply(delay_seconds=1)])
    assert provider.calls == provider.cancelled == 2
    assert all(i.reasonMethod == 'TEMPLATE' for i in result.course.items)


def test_total_stage_budget_cancels_attempt_without_waiting_for_each_place(example):
    provider = FakeProvider([FakeReply(delay_seconds=1)])
    result = asyncio.run(ExplanationGenerator(AIService(provider), example[0], total_budget_seconds=0.05).explain(example[1]))
    assert provider.calls == provider.cancelled and provider.calls <= 1
    assert result.warnings[0]['code'] == 'AI_FALLBACK'


def test_zero_remaining_budget_uses_template_without_model_call(example):
    repo, course = example
    provider = FakeProvider([])
    result = asyncio.run(ExplanationGenerator(AIService(provider), repo).explain(course, remaining_seconds=0))
    assert provider.calls == 0 and all(i.reasonMethod == 'TEMPLATE' for i in result.course.items)


def test_context_contains_only_final_places_bounded_overview_and_categories(example):
    repo, course = example
    p = repo.places[course.items[0].place.id]
    repo.places[p.id] = replace(p, overview='가' * 300, price_text='private-price', accessibility=replace(p.accessibility, raw='private-raw'))
    repo.places['synthetic:not-selected'] = synthetic_place('not-selected')
    class Inspect:
        async def complete(self, request):
            assert request.user_message is None
            assert request.context.place_ids == tuple(i.place.id for i in course.items)
            assert request.context.mobility == ('INJURY',)
            assert len(request.context.places[0].overview) == 200
            assert 'private-price' not in str(request.context.places)
            assert all(not hasattr(p, 'raw') and not hasattr(p, 'profile') for p in request.context.places)
            return output(course)
    result = asyncio.run(ExplanationGenerator(AIService(Inspect()), repo).explain(course, ('INJURY',)))
    assert all(i.reasonMethod == 'LLM' for i in result.course.items)


@pytest.mark.parametrize('mutation', ['delete', 'hours', 'hours-same-text', 'accessibility', 'source'])
def test_repository_change_during_model_call_rejects_stale_course(example, mutation):
    repo, course = example
    class Mutate:
        async def complete(self, request):
            p = repo.places[course.items[0].place.id]
            if mutation == 'delete': del repo.places[p.id]
            if mutation == 'hours':
                from app.domain.place import OpenHoursRecord
                repo.places[p.id] = replace(p, open_hours=OpenHoursRecord({'fri': []}, '휴무'))
            if mutation == 'hours-same-text':
                from app.domain.place import OpenHoursRecord
                repo.places[p.id] = replace(p, open_hours=OpenHoursRecord({'fri': []}, p.open_hours.text))
            if mutation == 'accessibility': repo.places[p.id] = replace(p, accessibility=replace(p.accessibility, wheelchair=False))
            if mutation == 'source': repo.sources[p.source_id] = replace(repo.sources[p.source_id], provider='changed')
            return output(course)
    with pytest.raises(ValueError):
        asyncio.run(ExplanationGenerator(AIService(Mutate()), repo).explain(course))


def test_database_failure_is_not_an_ai_template_success(example):
    repo, course = example
    repo.get_place = lambda key: (_ for _ in ()).throw(RuntimeError('private-sentinel'))
    provider = FakeProvider([])
    with pytest.raises(RuntimeError):
        asyncio.run(ExplanationGenerator(AIService(provider), repo).explain(course))
    assert provider.calls == 0


def test_external_cancellation_propagates(example):
    async def scenario():
        provider = FakeProvider([FakeReply(delay_seconds=100)])
        task = asyncio.create_task(ExplanationGenerator(AIService(provider), example[0]).explain(example[1]))
        for _ in range(1000):
            if provider.calls: break
            await asyncio.sleep(0.001)
        assert provider.calls == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert provider.cancelled == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('budget', [True, 0, -1, 13, float('nan'), float('inf')])
def test_invalid_budget_is_rejected(example, budget):
    with pytest.raises(ValueError): ExplanationGenerator(None, example[0], total_budget_seconds=budget)
