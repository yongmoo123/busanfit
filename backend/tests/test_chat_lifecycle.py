"""Late extraction errors cannot leak details or override newer session state."""
import pytest
from fastapi.testclient import TestClient
from app.application.extraction import Analysis, blank_profile
from test_chat_extraction import enabled_app
from test_chat_policy import ready


@pytest.mark.parametrize('action', ['discard', 'revision', 'none'])
@pytest.mark.parametrize('failure', [False, True])
def test_late_chat_result_or_extractor_error_respects_current_state(action, failure, caplog):
    app = enabled_app()
    with TestClient(app) as client:
        sid = client.post('/api/sessions', json={}).json()['sessionId']
        store = app.state.sessions
        store.commit_profile(sid, 0, profile=ready(), history=[])
        class Extract:
            async def extract(self, message):
                if action == 'discard': store.clear()
                elif action == 'revision':
                    state = store.check_current(sid, 1)
                    store.commit_profile(sid, 1, profile=state.profile, history=[])
                if failure: raise RuntimeError('private-sentinel')
                return Analysis(blank_profile())
        app.state.extractor = Extract()
        response = client.post('/api/chat', json={'sessionId': sid,
            'expectedProfileRevision': 1, 'message': '[가상] 조건 확인'})
        assert response.status_code == (410 if action == 'discard' else 409 if action == 'revision' else 500 if failure else 200)
        assert 'private-sentinel' not in response.text + caplog.text
