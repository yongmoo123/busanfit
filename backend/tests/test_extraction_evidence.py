"""#84 High regressions: schema-valid hallucinations, synthetic providers only."""
import asyncio
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from app.ai.fake import FakeProvider, FakeReply
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor, blank_profile
from app.constraints.chat_parser import ChatRuleParser
from app.main import create_app
from test_courses import CONTRACT


WINDOW = {'startAt': '2026-11-14T15:00:00+09:00', 'endAt': '2026-11-14T18:00:00+09:00'}


def reply(*, area='HAEUNDAE', family=None, hints=None):
    profile = blank_profile()
    profile['area'] = {'value': area, 'source': 'USER', 'strength': 'HARD'}
    profile['timeWindow'] = {'value': dict(WINDOW), 'source': 'USER', 'strength': 'HARD'}
    if family is not None:
        profile['companions'] = {'value': family, 'source': 'USER', 'strength': 'SOFT'}
    return {'profile': profile, 'companionHints': hints or {}}


def extractor(*replies):
    return AIConditionExtractor(AIService(FakeProvider([FakeReply(json.dumps(r)) for r in replies])), ChatRuleParser())


def app_for(extraction):
    from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
    return create_app(extractor=extraction,
        profile_support=ProfileSupport(True, frozenset(INITIAL_FIELDS), True))


def chat(client, sid, message, revision=0):
    response = client.post('/api/chat', json={'sessionId': sid, 'expectedProfileRevision': revision, 'message': message})
    assert response.status_code == 200, response.text
    CONTRACT['check'](response.json(), CONTRACT['schemas']['ChatResponse'])
    return response.json()


def test_ex14_invented_end_cannot_become_ready_or_generate_course(caplog):
    message = '[가상] 토요일 오후 3시부터 광안리에서 놀 거예요.'
    app = app_for(extractor(reply(area='GWANGALLI')))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        body = chat(client, sid, message)
        assert body['status'] == 'NEEDS_INPUT'
        assert body['profile']['area']['value'] == 'GWANGALLI'
        assert body['profile']['timeWindow'] == {'value': None, 'source': 'UNSET', 'strength': 'HARD'}
        assert [q['field'] for q in body['questions']] == ['timeWindow']
        generated = client.post('/api/courses', json={'sessionId': sid, 'profileRevision': body['profileRevision']})
        assert generated.status_code == 422 and generated.json()['error']['code'] == 'PROFILE_INCOMPLETE'
        state = app.state.sessions.check_current(sid, body['profileRevision'])
        assert state.history == [] and message not in caplog.text + str(state.__dict__)


@pytest.mark.parametrize('channel', ['profile', 'hints', 'both'])
def test_ex31_invented_count_and_absence_reach_dec022_infant_question(channel):
    family = {'type': 'FAMILY', 'count': 1, 'hasInfant': False}
    invented = reply(family=family if channel != 'hints' else None,
                     hints=family if channel != 'profile' else None)
    invented['profile']['timeWindow']['value'] = {
        'startAt': '2026-11-15T13:00:00+09:00', 'endAt': '2026-11-15T17:00:00+09:00'}
    # Valid explicit time range; only invented family subfields should be removed.
    message = '[가상] 일요일 오후 1시부터 5시까지 해운대에서 가족끼리 놀려고요.'
    app = app_for(extractor(invented))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        body = chat(client, sid, message)
        assert body['status'] == 'NEEDS_INPUT'
        assert [q['field'] for q in body['questions']] == ['companions']
        assert body['questions'][0]['message'] == '영유아도 함께 가나요?'
        assert body['profile']['companions']['value'] is None
        state = app.state.sessions.check_current(sid, body['profileRevision'])
        assert state.companion_hints['type'] == 'FAMILY'
        assert 'count' not in state.companion_hints and 'hasInfant' not in state.companion_hints
        assert state.companion_hints['_infantAsked'] is True
        assert client.post('/api/courses', json={'sessionId': sid,
            'profileRevision': body['profileRevision']}).status_code == 422


def test_first_infant_answer_true_adds_stroller_without_making_up_count():
    family = {'type': 'FAMILY', 'count': 1, 'hasInfant': False}
    first = reply(family=family)
    second = {'profile': blank_profile(), 'companionHints': {'hasInfant': True}}
    app = app_for(extractor(first, second))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        a = chat(client, sid, '일요일 13시부터 17시까지 해운대에서 가족끼리')
        b = chat(client, sid, '네 아기도 같이 가요', a['profileRevision'])
        assert b['status'] == 'READY' and b['questions'] == []
        assert b['profile']['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
        hints = app.state.sessions.check_current(sid, b['profileRevision']).companion_hints
        assert 'count' not in hints and hints['hasInfant'] is True


def test_dec022_unanswered_question_is_once_and_warns_not_provider_default():
    family = {'type': 'FAMILY', 'count': 1, 'hasInfant': False}
    first = reply(family=family)
    # The model repeats its invented values on an unrelated follow-up.
    second = reply(family=family)
    app = app_for(extractor(first, second))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        a = chat(client, sid, '일요일 13시부터 17시까지 해운대에서 가족끼리')
        assert a['status'] == 'NEEDS_INPUT'
        b = chat(client, sid, '그냥 진행해 주세요', a['profileRevision'])
        assert b['status'] == 'READY' and b['profile']['companions']['value'] is None
        hints = app.state.sessions.check_current(sid, b['profileRevision']).companion_hints
        assert hints['_infantAssumedAbsent'] is True and 'count' not in hints
        assert any('영유아 동반이면' in w['message'] for w in b['warnings'])


@pytest.mark.parametrize('message', ['가족 4명이 아기와 함께 가요', '가족 네 명이 아기랑 가요',
                                     '남편과 아기까지 넷이 가요'])
def test_explicit_count_and_infant_positive_are_preserved(message):
    family = {'type': 'FAMILY', 'count': 4, 'hasInfant': True}
    response = asyncio.run(extractor(reply(family=family)).extract(message))
    assert response.profile['companions']['value'] == family


@pytest.mark.parametrize('message', ['가족 3명이고 아기는 없어요', '가족 셋이 가요. 영유아는 동반하지 않아요'])
def test_explicit_negative_infant_is_preserved(message):
    family = {'type': 'FAMILY', 'count': 3, 'hasInfant': False}
    response = asyncio.run(extractor(reply(family=family)).extract(message))
    assert response.profile['companions']['value'] == family


@pytest.mark.parametrize('text', ['토요일 오후 3시부터 6시까지', '15:00~18:00',
                                '오후 3시-6시', '오후 3시부터 세 시간 동안 놀래요'])
def test_explicit_end_or_duration_does_not_drop_valid_window(text):
    response = asyncio.run(extractor(reply()).extract(text))
    assert response.profile['timeWindow']['value'] == WINDOW
    assert 'timeWindow' not in response.unconfirmed_fields


def test_new_partial_time_does_not_overwrite_existing_user_window():
    app = app_for(extractor(reply(), reply()))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        a = chat(client, sid, '토요일 15시부터18시까지 해운대')
        b = chat(client, sid, '오후 4시부터로 바꿔 주세요', a['profileRevision'])
        assert b['status'] == 'NEEDS_INPUT'
        assert b['profile']['timeWindow'] == a['profile']['timeWindow']
        assert b['questions'][0]['field'] == 'timeWindow'


def test_unrelated_message_does_not_replace_or_question_confirmed_fields():
    family = {'type': 'FAMILY', 'count': 4, 'hasInfant': True}
    invented = {'type': 'FAMILY', 'count': 1, 'hasInfant': False}
    app = app_for(extractor(reply(family=family), reply(family=invented)))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        a = chat(client, sid, '토요일 15시부터18시까지 가족4명이 아기랑 해운대')
        b = chat(client, sid, '그대로 진행해 주세요', a['profileRevision'])
        assert b['status'] == 'READY'
        assert b['profile']['timeWindow'] == a['profile']['timeWindow']
        assert b['profile']['companions'] == a['profile']['companions']
        assert b['profile']['mobility'] == a['profile']['mobility']


@pytest.mark.parametrize('text', ['오후 3시부터, 종료 시각은 미정이에요', '오후 3시부터 6시까지는 아니에요'])
def test_missing_or_negated_end_is_not_positive_evidence(text):
    response = asyncio.run(extractor(reply()).extract(text))
    assert response.profile['timeWindow']['value'] is None
    assert 'timeWindow' in response.unconfirmed_fields


def test_clock_minutes_are_not_people_count_or_infant_evidence():
    family = {'type': 'FAMILY', 'count': 30, 'hasInfant': True}
    response = asyncio.run(extractor(reply(family=family)).extract(
        '가족끼리 13시30분부터17시까지 아기자기한 곳에 갈래요'))
    assert response.profile['companions']['value'] is None
    assert response.companion_hints == {'type': 'FAMILY'}


def test_unsupported_family_claim_cannot_skip_question_by_using_solo_type():
    family = {'type': 'SOLO', 'count': 1, 'hasInfant': False}
    app = app_for(extractor(reply(family=family)))
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        body = chat(client, sid, '13시부터17시까지 해운대 가족끼리')
        assert body['status'] == 'NEEDS_INPUT'
        state = app.state.sessions.check_current(sid, body['profileRevision'])
        assert state.companion_hints['type'] == 'FAMILY' and 'count' not in state.companion_hints


def test_conflicting_infant_statement_needs_confirmation_instead_of_false_absence():
    family = {'type': 'FAMILY', 'count': 3, 'hasInfant': False}
    response = asyncio.run(extractor(reply(family=family)).extract('가족3명이 아기랑 가요'))
    assert response.profile['companions']['value'] is None
    assert 'hasInfant' not in response.companion_hints
    assert 'companions' in response.unconfirmed_fields


@pytest.mark.parametrize('kind', ['FRIENDS', 'FAMILY'])
def test_negated_family_mention_does_not_force_family_type(kind):
    group = {'type': kind, 'count': 4, 'hasInfant': False}
    response = asyncio.run(extractor(reply(family=group)).extract('가족은 아니고 친구4명이에요'))
    if kind == 'FRIENDS':
        assert response.profile['companions']['value'] == group
    else:
        assert response.profile['companions']['value'] is None
        assert 'companions' in response.unconfirmed_fields
