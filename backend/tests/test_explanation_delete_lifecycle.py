"""Late explanation success/error cannot resurrect a session deleted by HTTP."""
import json
import httpx
import pytest
from app.ai.service import AIService
from app.explanations.generator import ExplanationGenerator
from test_courses import env, seed, generate


@pytest.mark.parametrize('failure', [False, True])
def test_http_delete_during_explanation_wins_over_model_result(env, failure):
    seed(env)
    class Delete:
        async def complete(self, request):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env['app']), base_url='http://test') as client:
                assert (await client.delete('/api/sessions/' + env['sid'])).status_code == 204
            if failure: raise RuntimeError('private-sentinel')
            return json.dumps({'items': [{'placeId': p.place_id, 'facts': ['CATEGORY']} for p in request.context.places]})
    env['app'].state.explanation_generator = ExplanationGenerator(AIService(Delete()), env['repository'])
    response = generate(env)
    assert response.status_code == 410 and 'private-sentinel' not in response.text
    assert env['client'].delete('/api/sessions/' + env['sid']).status_code == 204
