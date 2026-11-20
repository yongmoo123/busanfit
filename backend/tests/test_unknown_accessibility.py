"""#30/#31ii synthetic contract, consent, independent hard checks and lifecycle."""
from dataclasses import replace
from pathlib import Path
import runpy

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.api.course_models import Suggestion
from app.api.profile_models import Profile
from app.application.course_service import CourseService
from app.application.extraction import Analysis, blank_profile
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.application.suggestions import build_unknown_accessibility_suggestions
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.courses.scheduler import CourseScheduler
from app.courses.validator import CourseValidator
from app.domain.course import RetrievalResult
from app.domain.place import OpenHoursRecord, PlaceCandidate
from app.main import create_app

CONTRACT = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'contracts/validate_contract.py'))


def support(enabled=True):
    return ProfileSupport(True, frozenset(INITIAL_FIELDS), True, enabled)


def profile(modes=('WHEELCHAIR',), consent=False):
    values = blank_profile()
    for name, value in {'area': 'HAEUNDAE', 'timeWindow': {
        'startAt': '2026-11-21T13:00:00+09:00', 'endAt': '2026-11-21T18:00:00+09:00'},
        'mobility': list(modes)}.items():
        values[name] = {'value': value, 'source': 'USER', 'strength': 'HARD'}
    values['includeUnknownAccessibility'] = consent
    return Profile.model_validate(values)


class PoolRetriever:
    def __init__(self, known, pool, *, distance=100):
        self.known, self.pool, self.distance = known, pool, distance

    def retrieve(self, profile):
        return RetrievalResult(tuple(PlaceCandidate(p, 100) for p in self.known),
            unknown_accessibility_candidates=tuple(PlaceCandidate(p, self.distance) for p in self.pool))


def setup(known=None, unknown=None, **kwargs):
    known = known if known is not None else [synthetic_place('a'), synthetic_place('b')]
    unknown = unknown if unknown is not None else [synthetic_place('c', wheelchair=None, stroller=None)]
    repo = FakeRepository(known + unknown)
    retriever = PoolRetriever(known, unknown, **kwargs)
    return CourseService(retriever, FakeTravel(), repo), repo


def generate(service, value):
    return service.generate(value, 1, build_profile_capabilities(support()))


def test_proposal_requires_actual_accessibility_only_candidates_without_mutation():
    service, _ = setup()
    value = profile()
    before = value.model_dump()
    result = generate(service, value)
    assert result.course.validation.status == 'PASSED'
    assert [s.type for s in result.suggestions] == ['EDIT_PROFILE', 'INCLUDE_UNKNOWN_ACCESSIBILITY']
    assert result.excluded_unknown == {'count': 1, 'fields': ['mobility.wheelchair']}
    assert value.model_dump() == before
    assert all(item.place.accessibility.wheelchair is True for item in result.course.items)


@pytest.mark.parametrize('modes', [('WHEELCHAIR',), ('STROLLER',), ('INJURY',), ('WHEELCHAIR', 'STROLLER')])
def test_consented_unknown_is_conditional_and_null_is_preserved(modes):
    service, _ = setup(known=[synthetic_place('a')])
    denied = generate(service, profile(modes))
    assert denied.course is None
    assert [s.type for s in denied.suggestions] == ['INCLUDE_UNKNOWN_ACCESSIBILITY']
    result = generate(service, profile(modes, True))
    assert result.course.validation.status == 'CONDITIONAL'
    assert result.course.validation.routeAccessibility == 'UNVERIFIED'
    fields = result.course.validation.unverifiedFields
    assert ('mobility.stroller' in fields) == ('STROLLER' in modes)
    assert ('mobility.wheelchair' in fields) == bool(set(modes) & {'WHEELCHAIR', 'INJURY'})
    assert result.excluded_unknown == {'count': 0, 'fields': []}
    warnings = [w for w in result.warnings if w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED']
    assert warnings[0]['placeIds'] == ['synthetic:c']
    assert result.course.items[-1].place.accessibility.wheelchair is None
    assert not any(s.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY' for s in result.suggestions)


@pytest.mark.parametrize('fault', ['false', 'hours', 'address', 'area', 'radius', 'distance-unknown',
                                  'excluded-category', 'mixed-false', 'indoor'])
def test_consent_never_bypasses_other_hard_failures(fault):
    unknown = synthetic_place('c', wheelchair=None)
    value = profile(consent=True)
    if fault == 'false': unknown = replace(unknown, accessibility=replace(unknown.accessibility, wheelchair=False))
    if fault == 'hours': unknown = replace(unknown, open_hours=OpenHoursRecord(None, '[가상] 해석 못 한 원문'))
    if fault == 'address': unknown = replace(unknown, address='')
    if fault == 'area': unknown = replace(unknown, area='NAMPO')
    if fault == 'mixed-false':
        value = profile(('WHEELCHAIR', 'STROLLER'), True)
        unknown = replace(unknown, accessibility=replace(unknown.accessibility, stroller=False))
    if fault == 'excluded-category': value.excludedCategories.value, value.excludedCategories.source = ['SHOPPING'], 'USER'; unknown = replace(unknown, category='SHOPPING')
    if fault == 'indoor':
        value.indoorPreference.value, value.indoorPreference.source = 'INDOOR', 'USER'
        value.indoorPreference.strength = 'HARD'
        unknown = replace(unknown, indoor=None)
    service, _ = setup(known=[synthetic_place('a')], unknown=[unknown],
        distance=1501 if fault == 'radius' else None if fault == 'distance-unknown' else 100)
    if fault == 'indoor':
        caps = build_profile_capabilities(support())
        caps.supportedProfileFields.append('indoorPreference')
        result = service.generate(value, 1, caps)
    else:
        result = generate(service, value)
    assert result.course is None
    assert not any(w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED' for w in result.warnings)
    # A successful baseline must not offer inclusion of an ineligible pool item.
    value.includeUnknownAccessibility = False
    baseline, _ = setup(unknown=[unknown], distance=1501 if fault == 'radius' else None if fault == 'distance-unknown' else 100)
    result = baseline.generate(value, 1, caps) if fault == 'indoor' else generate(baseline, value)
    assert result.course is not None
    assert not any(s.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY' for s in result.suggestions)
    if fault in ('false', 'area', 'radius', 'excluded-category', 'mixed-false'):
        assert result.excluded_unknown['count'] == 0


def test_generic_excluded_count_alone_does_not_generate_inclusion_action():
    places = [synthetic_place('a'), synthetic_place('b')]
    service = CourseService(FakeRetriever(places, unknown_ids=['synthetic:other'], unknown_fields=['mobility.wheelchair']),
                            FakeTravel(), FakeRepository(places))
    assert not any(s.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY' for s in generate(service, profile()).suggestions)


@pytest.mark.parametrize('eligible', [False, True])
def test_insufficient_http_response_only_offers_eligible_inclusion(eligible):
    service, _ = setup(known=[synthetic_place('a')], unknown=None if eligible else [])
    with TestClient(create_app(course_service=service, profile_support=support())) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        saved = client.put(f'/api/sessions/{sid}/profile',
            json={'profile': profile().model_dump(mode='json'), 'expectedProfileRevision': 0})
        assert saved.status_code == 200
        response = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': 1})
        assert response.status_code == 200, response.text
        body = response.json()
        CONTRACT['check'](body, CONTRACT['schemas']['CourseResponse'])
        assert body['status'] == 'INSUFFICIENT_PLACES' and body['course'] is None
        assert [s['type'] for s in body['suggestions']] == (['INCLUDE_UNKNOWN_ACCESSIBILITY'] if eligible else [])


def test_eligibility_is_rechecked_after_course_source_assembly():
    service, repo = setup()
    original = repo.get_sources
    def changed(ids):
        old = repo.places['synthetic:c']
        repo.places['synthetic:c'] = replace(old, accessibility=replace(old.accessibility, wheelchair=False))
        return original(ids)
    repo.get_sources = changed
    result = generate(service, profile())
    assert result.course is not None
    assert not any(s.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY' for s in result.suggestions)
    assert result.excluded_unknown == {'count': 0, 'fields': []}


def test_grade_verified_cannot_hide_the_required_null_field():
    service, _ = setup(known=[synthetic_place('a')], unknown=[synthetic_place('c', wheelchair=None, stroller=True)])
    result = generate(service, profile(consent=True))
    assert result.course.validation.status == 'CONDITIONAL'
    item = next(item for item in result.course.items if item.place.id == 'synthetic:c')
    assert item.place.accessibility.grade == 'VERIFIED' and item.place.accessibility.wheelchair is None
    assert any(w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED' for w in result.warnings)


def test_inclusion_keeps_candidate_cap_and_injury_walking_limit():
    service, _ = setup(known=[synthetic_place('a')])
    service.travel_provider = FakeTravel(minutes=11)
    assert generate(service, profile(('INJURY',), True)).course is None
    service, _ = setup()
    service.settings = replace(service.settings, max_candidates=2)
    result = generate(service, profile(consent=True))
    assert len(result.course.items) == 2
    assert result.course.validation.status == 'PASSED'
    assert any(w['code'] == 'CANDIDATE_LIMIT' for w in result.warnings)


def test_inclusion_reserves_third_slot_after_two_default_chips():
    service, _ = setup()
    value = profile()
    for name in ('area', 'timeWindow'):
        getattr(value, name).source = 'DEFAULT'
    result = generate(service, value)
    assert [s.field for s in result.suggestions] == ['area', 'transport', 'includeUnknownAccessibility']
    service, _ = setup(unknown=[])
    assert [s.field for s in generate(service, value).suggestions] == ['area', 'transport', 'timeWindow']


def test_confirmed_places_stay_passed_even_with_flag_true_and_ordinary_mode_needs_no_consent():
    service, _ = setup(unknown=[])
    result = generate(service, profile(consent=True))
    assert result.course.validation.status == 'PASSED'
    assert not any(w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED' for w in result.warnings)
    service, _ = setup(known=[synthetic_place('a', wheelchair=None), synthetic_place('b', wheelchair=None)], unknown=[])
    result = generate(service, profile(()))
    assert result.course.validation.status == 'PASSED'
    assert not any(s.type == 'INCLUDE_UNKNOWN_ACCESSIBILITY' for s in result.suggestions)


def test_independent_validator_cannot_hide_false_or_other_violations():
    service, repo = setup(known=[synthetic_place('a')])
    value = profile(consent=True)
    value.transport.value, value.transport.source = 'WALK', 'USER'
    places = [repo.places['synthetic:a'], repo.places['synthetic:c']]
    candidates = tuple(PlaceCandidate(p, 100) for p in places)
    travel = lambda *args: type('Estimate', (), {'minutes': 5})()
    plan = CourseScheduler().schedule(candidates, value, travel)
    result = CourseValidator(repo).validate(plan, value, {p.id: 100 for p in places}, travel,
                                          allow_unknown_accessibility=True)
    assert result.accepted and not result.passed and result.unverified_fields == ('mobility.wheelchair',)
    repo.places['synthetic:c'] = replace(places[1], accessibility=replace(places[1].accessibility, wheelchair=False))
    result = CourseValidator(repo).validate(plan, value, {p.id: 100 for p in places}, travel,
                                          allow_unknown_accessibility=True)
    assert not result.accepted
    assert any(v.code == 'ACCESSIBILITY_REJECTED' for v in result.violations)


def test_facts_changing_during_source_assembly_are_rechecked():
    service, repo = setup(known=[synthetic_place('a')])
    original = repo.get_sources
    def changed(ids):
        old = repo.places['synthetic:c']
        repo.places['synthetic:c'] = replace(old, accessibility=replace(old.accessibility, wheelchair=False))
        return original(ids)
    repo.get_sources = changed
    result = generate(service, profile(consent=True))
    assert result.course is None
    assert not any(w['code'] == 'UNKNOWN_ACCESSIBILITY_INCLUDED' for w in result.warnings)
    assert result.excluded_unknown['count'] == 0


@pytest.mark.parametrize('kind,field', [('EDIT_PROFILE', 'includeUnknownAccessibility'),
                                      ('INCLUDE_UNKNOWN_ACCESSIBILITY', 'mobility')])
def test_suggestion_discriminator_rejects_crossed_action_and_field(kind, field):
    data = {'id': 'synthetic', 'type': kind, 'label': '가상', 'field': field}
    with pytest.raises(ValidationError): Suggestion.model_validate(data)
    with pytest.raises((AssertionError, ValueError, TypeError)):
        CONTRACT['check'](data, CONTRACT['schemas']['Suggestion'])
    with pytest.raises((AssertionError, ValueError, TypeError)):
        CONTRACT['check'](data, Suggestion.model_json_schema())


def test_http_put_consent_then_post_new_revision_and_explicit_revoke():
    service, repo = setup()
    app = create_app(course_service=service, profile_support=support())
    with TestClient(app) as client:
        session = client.post('/api/sessions', json={}).json()
        assert session['capabilities']['supportsUnknownAccessibilityInclusion'] is True
        sid = session['sessionId']
        def save(p, rev):
            return client.put(f'/api/sessions/{sid}/profile', json={'profile': p, 'expectedProfileRevision': rev})
        def course(rev): return client.post('/api/courses', json={'sessionId': sid, 'profileRevision': rev})
        initial = save(profile().model_dump(mode='json'), 0).json()
        first = course(1).json()
        action = first['suggestions'][-1]
        assert action['type'] == 'INCLUDE_UNKNOWN_ACCESSIBILITY'
        assert app.state.sessions.check_current(sid, 1).profile['includeUnknownAccessibility'] is False
        accepted = initial['profile'] | {'includeUnknownAccessibility': True}
        saved = save(accepted, 1)
        assert saved.status_code == 200 and saved.json()['profileRevision'] == 2
        assert saved.json()['profile']['mobility'] == initial['profile']['mobility']
        assert course(1).status_code == 409
        result = course(2)
        assert result.status_code == 200, result.text
        CONTRACT['check'](result.json(), CONTRACT['schemas']['CourseResponse'])
        assert result.json()['course']['validation']['status'] == 'CONDITIONAL'
        assert not any(s['type'] == action['type'] for s in result.json()['suggestions'])
        # POST failure does not roll back the successful PUT; POST retry keeps revision.
        real_retriever = service.retriever
        class Failing:
            def retrieve(self, p): raise RuntimeError('synthetic failure')
        service.retriever = Failing()
        assert course(2).status_code == 500
        assert app.state.sessions.check_current(sid, 2).profile['includeUnknownAccessibility'] is True
        service.retriever = real_retriever
        assert course(2).status_code == 200
        revoked = saved.json()['profile'] | {'includeUnknownAccessibility': False}
        assert save(revoked, 2).json()['profileRevision'] == 3
        assert course(3).json()['course']['validation']['status'] == 'PASSED'
        assert client.delete(f'/api/sessions/{sid}').status_code == 204
        assert course(3).status_code == 410


def test_ordinary_root_remains_disabled_and_rejects_true_without_revision_change():
    assert build_profile_capabilities().supportsUnknownAccessibilityInclusion is False
    assert not create_app().state.capabilities.supportsUnknownAccessibilityInclusion
    service, _ = setup()
    with TestClient(create_app(course_service=service, profile_support=support(False))) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        response = client.put(f'/api/sessions/{sid}/profile',
            json={'profile': profile(consent=True).model_dump(mode='json'), 'expectedProfileRevision': 0})
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'UNSUPPORTED_CONSTRAINT'


def test_new_pool_is_an_optional_typed_port_extension():
    assert RetrievalResult(()).unknown_accessibility_candidates == ()
    with pytest.raises(ValueError): RetrievalResult((), unknown_accessibility_candidates=['bad'])


@pytest.mark.parametrize('channel', ['card', 'chat', 'card-without-extractor'])
@pytest.mark.parametrize('change', ['add', 'remove', 'reorder', 'source'])
def test_mobility_consent_reset_is_shared_by_card_and_chat(channel, change):
    modes = ('WHEELCHAIR', 'STROLLER') if change in ('remove', 'reorder') else ('STROLLER',)
    old = profile(modes, True).model_dump(mode='json')
    old['transport'] = {'value': 'WALK', 'source': 'USER', 'strength': 'SOFT'}
    if change == 'source':
        old['mobility']['source'] = 'DEFAULT'
    incoming = profile((), True).model_dump(mode='json')
    incoming['mobility']['value'] = {
        'add': ['STROLLER', 'INJURY'], 'remove': [],
        'reorder': ['STROLLER', 'WHEELCHAIR'], 'source': ['STROLLER'],
    }[change]
    analysis = Analysis(blank_profile())
    analysis.profile['mobility'] = incoming['mobility']
    class Extractor:
        async def extract(self, message): return analysis
    app = create_app(extractor=Extractor(), profile_support=support())
    if channel == 'card-without-extractor':
        app.state.extractor = None
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        app.state.sessions.commit_profile(sid, 0, profile=old, history=[])
        if channel == 'chat':
            response = client.post('/api/chat', json={'sessionId': sid, 'expectedProfileRevision': 1,
                                                      'message': '[가상] 이동제약 수정'})
        else:
            # Echoing true cannot carry previous consent across a value change.
            response = client.put(f'/api/sessions/{sid}/profile',
                json={'profile': old | {'mobility': incoming['mobility']}, 'expectedProfileRevision': 1})
        assert response.status_code == 200, response.text
        expected = change in ('reorder', 'source')
        assert response.json()['profile']['includeUnknownAccessibility'] is expected
        assert app.state.sessions.check_current(sid, 2).profile['includeUnknownAccessibility'] is expected


@pytest.mark.parametrize('channel', ['card', 'chat'])
@pytest.mark.parametrize('had_infant', [False, True])
def test_infant_default_addition_and_removal_reset_consent_after_normalization(channel, had_infant):
    old = profile((), True).model_dump(mode='json')
    old['mobility'] = {'value': ['STROLLER'] if had_infant else None,
                       'source': 'DEFAULT' if had_infant else 'UNSET', 'strength': 'HARD'}
    old['transport'] = {'value': 'WALK', 'source': 'USER', 'strength': 'SOFT'}
    old['companions'] = {'value': {'type': 'FAMILY', 'count': 3, 'hasInfant': had_infant},
                          'source': 'USER', 'strength': 'SOFT'}
    companions = {**old['companions'], 'value': {**old['companions']['value'], 'hasInfant': not had_infant}}
    analysis = Analysis(blank_profile())
    analysis.profile['companions'] = companions
    class Extractor:
        async def extract(self, message): return analysis
    app = create_app(extractor=Extractor(), profile_support=support())
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        app.state.sessions.commit_profile(sid, 0, profile=old, history=[])
        if channel == 'chat':
            result = client.post('/api/chat', json={'sessionId': sid, 'expectedProfileRevision': 1,
                                                  'message': '[가상] 영유아 동반 변경'})
        else:
            result = client.put(f'/api/sessions/{sid}/profile',
                json={'profile': old | {'companions': companions}, 'expectedProfileRevision': 1})
        assert result.status_code == 200, result.text
        saved = result.json()['profile']
        assert saved['mobility']['value'] == (None if had_infant else ['STROLLER'])
        assert saved['includeUnknownAccessibility'] is False
        # Re-consent is a separate PUT against the returned normalized profile/revision.
        consent = client.put(f'/api/sessions/{sid}/profile',
            json={'profile': saved | {'includeUnknownAccessibility': True}, 'expectedProfileRevision': 2})
        assert consent.status_code == 200, consent.text
        assert consent.json()['profile']['includeUnknownAccessibility'] is True


@pytest.mark.parametrize('before,after', [(None, []), ([], None)])
def test_unset_and_explicit_no_mobility_are_distinct_for_consent(before, after):
    from app.application.condition_policy import reset_changed_mobility_consent
    previous = profile(consent=True).model_dump(mode='json')
    previous['mobility']['value'] = before
    value = profile(consent=True)
    value.mobility.value = after
    assert reset_changed_mobility_consent(value, previous).includeUnknownAccessibility is False
