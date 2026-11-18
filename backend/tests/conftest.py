"""Tests never use a real developer key, even if the shell has one configured."""
import pytest


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
