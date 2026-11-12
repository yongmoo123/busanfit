"""Static policy fixture checks, not an implementation of the chat API."""
from copy import deepcopy

WARNING_CODES = {'AI_FALLBACK', 'UNCONFIRMED_CHANGE', 'UNSUPPORTED_TRANSPORT', 'STROLLER_NOT_APPLIED'}
CASE_IDS = {
    'transport-chat-partial', 'transport-put-rejected', 'transport-chat-accepted',
    'transport-put-preserves-pending',
    'stroller-auto', 'stroller-user-empty', 'stroller-user-injury',
    'stroller-remove-only', 'stroller-reset-unset', 'stroller-cancel-default',
    'fallback-both-missing', 'fallback-one-present', 'fallback-unconfirmed-change',
    'fallback-existing-ready', 'normal-missing',
}


def validate_case(case, spec, check):
    schemas = spec['components']['schemas']
    chat = case['operation'] == 'chat'
    check(case['request'], schemas['ChatRequest' if chat else 'ProfileUpdateRequest'])
    response = case['expectedResponse']
    before = case['before']
    if case['expectedHttp'] != 200:
        check(response, schemas['ErrorResponse'])
        assert case['expectedPendingFields'] == before['pendingFields']
        if case['expectedHttp'] == 503:
            assert case['fallbackUsed']
            assert response['error']['code'] == 'AI_UNAVAILABLE'
            for field in ('area', 'timeWindow'):
                assert before['profile'][field]['value'] is None
                assert case['extractedProfile'][field]['value'] is None
        elif case['expectedHttp'] == 422:
            assert not chat and response['error']['code'] == 'UNSUPPORTED_CONSTRAINT'
            assert response['error']['details'][0]['field'] == 'transport'
        else:
            raise AssertionError('unexpected fixture HTTP code')
        return
    check(response, schemas['ChatResponse' if chat else 'ProfileResponse'])
    assert response['profileRevision'] == before['profileRevision'] + 1
    assert response['sessionExpiresAt'] > before['sessionExpiresAt']
    profile = response['profile']
    for field, condition in profile.items():
        if not isinstance(condition, dict) or 'source' not in condition:
            continue
        assert (condition['value'] is None) == (condition['source'] == 'UNSET')
        if field in ('area', 'timeWindow'):
            assert condition['strength'] == 'HARD'
    codes = {warning['code'] for warning in response['warnings']}
    assert codes <= WARNING_CODES
    assert all(warning['placeIds'] == [] for warning in response['warnings'])
    pending = set(case['expectedPendingFields'])
    if response['status'] == 'READY':
        assert not pending and not response['questions']
        assert all(profile[f]['value'] is not None for f in ('area', 'timeWindow'))
    else:
        assert pending and 1 <= len(response['questions']) <= 2
        assert {q['field'] for q in response['questions']} <= pending
    if case['fallbackUsed']:
        assert 'AI_FALLBACK' in codes
    if 'UNSUPPORTED_TRANSPORT' in codes:
        assert 'transport' in pending
        assert profile['transport'] == before['profile']['transport']
        assert any(q['field'] == 'transport' for q in response['questions'])
        if not chat:
            assert case['request']['profile']['transport'] == before['profile']['transport']
            assert profile['timeWindow'] == case['request']['profile']['timeWindow']
    if 'UNCONFIRMED_CHANGE' in codes:
        assert pending and response['status'] == 'NEEDS_INPUT'
    if 'STROLLER_NOT_APPLIED' in codes:
        assert profile['companions']['value']['hasInfant'] is True
        assert profile['mobility']['source'] == 'USER'
        assert 'STROLLER' not in profile['mobility']['value']
        assert not any(q['field'] == 'mobility' for q in response['questions'])


def validate_cases(document, spec, check):
    cases = document['cases']
    assert len(cases) == len(CASE_IDS) and {c['id'] for c in cases} == CASE_IDS
    for case in cases:
        validate_case(case, spec, check)
    by_id = {case['id']: case for case in cases}
    def profile(name):
        return by_id[name]['expectedResponse']['profile']
    assert profile('transport-chat-partial')['area']['value'] == 'HAEUNDAE'
    assert profile('transport-chat-partial')['timeWindow']['value'] is not None
    assert profile('transport-chat-accepted')['transport']['source'] == 'USER'
    for name in ('stroller-auto', 'stroller-reset-unset'):
        assert profile(name)['mobility'] == {'value': ['STROLLER'], 'source': 'DEFAULT', 'strength': 'HARD'}
    assert profile('stroller-user-empty')['mobility']['value'] == []
    assert profile('stroller-user-injury')['mobility']['value'] == ['INJURY']
    assert profile('stroller-remove-only')['mobility']['value'] == ['WHEELCHAIR']
    assert profile('stroller-cancel-default')['mobility']['value'] is None
    preserved = by_id['fallback-unconfirmed-change']
    assert profile('fallback-unconfirmed-change') == preserved['before']['profile']
    assert by_id['normal-missing']['expectedResponse']['status'] == 'NEEDS_INPUT'
    assert by_id['fallback-existing-ready']['expectedResponse']['status'] == 'READY'

    # Prove that the checks reject drift, not just the supplied happy fixtures.
    for name, mutate in [
        ('transport-chat-partial', lambda c: c['expectedResponse']['profile']['transport'].update(value='WALK', source='DEFAULT')),
        ('transport-put-preserves-pending', lambda c: c['expectedResponse'].update(status='READY', questions=[])),
        ('fallback-both-missing', lambda c: c['before']['profile']['area'].update(value='HAEUNDAE', source='USER')),
        ('fallback-unconfirmed-change', lambda c: c['expectedResponse'].update(status='READY', questions=[])),
        ('stroller-user-empty', lambda c: c['expectedResponse']['profile']['mobility'].update(value=['STROLLER'])),
    ]:
        invalid = deepcopy(by_id[name])
        mutate(invalid)
        try:
            validate_case(invalid, spec, check)
        except (AssertionError, ValueError, TypeError):
            continue
        raise AssertionError('policy negative control accepted: ' + name)
