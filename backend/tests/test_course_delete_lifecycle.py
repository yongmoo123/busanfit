"""Existing DELETE #12 must win over late course retrieval success/errors."""
import pytest
from test_courses import env, seed, generate


@pytest.mark.parametrize('failure', [False, True])
def test_http_delete_during_retrieval_cannot_resurrect_course_session(env, failure):
    seed(env)
    original = env['retriever'].retrieve
    def retrieve(profile):
        assert env['client'].delete('/api/sessions/' + env['sid']).status_code == 204
        if failure: raise RuntimeError('private-sentinel')
        return original(profile)
    env['retriever'].retrieve = retrieve
    response = generate(env)
    assert response.status_code == 410 and 'private-sentinel' not in response.text
    assert env['client'].delete('/api/sessions/' + env['sid']).status_code == 204
