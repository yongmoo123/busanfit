"""Cancellable Gemini REST adapter; no payloads or provider errors are logged."""
import os
import re

import httpx

from app.ai.service import AIRequest


class GeminiProvider:
    def __init__(self, api_key: str, model: str, *, transport=None):
        if not api_key or not re.fullmatch(r'gemini-[a-zA-Z0-9.-]+', model):
            raise ValueError('Gemini key and valid model name are required')
        self._api_key, self._model, self._transport = api_key, model, transport

    async def complete(self, request: AIRequest) -> str:
        try:
            return await self._generate(request)
        except httpx.TimeoutException:
            raise TimeoutError('provider timeout') from None

    async def _generate(self, request: AIRequest) -> str:
        # AIService owns the total per-attempt deadline and the single retry.
        async with httpx.AsyncClient(transport=self._transport, timeout=10,
                                     follow_redirects=False, trust_env=False) as client:
            response = await client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent',
                headers={'x-goog-api-key': self._api_key},
                json={
                    'systemInstruction': {'parts': [{'text': request.system_prompt}]},
                    'contents': [{'role': 'user', 'parts': [{'text': request.user_message}]}],
                    'generationConfig': {'responseMimeType': 'application/json',
                                         'responseJsonSchema': request.output_schema},
                },
            )
            if response.status_code != 200:
                raise RuntimeError('provider unavailable')
            try:
                candidate = response.json()['candidates'][0]
                if candidate.get('finishReason') != 'STOP':
                    raise ValueError
                parts = candidate['content']['parts']
                text = ''.join(part['text'] for part in parts if not part.get('thought'))
                if not text.strip():
                    raise ValueError
                return text
            except (KeyError, IndexError, TypeError, ValueError):
                raise RuntimeError('invalid provider response') from None


class UnconfiguredProvider:
    async def complete(self, request: AIRequest) -> str:
        raise RuntimeError('provider is not configured')


def configured_provider():
    # Load .env through uvicorn --env-file backend/.env; never read/print keys here.
    key = os.environ.get('GEMINI_API_KEY', '')
    model = os.environ.get('GEMINI_MODEL', '')
    return GeminiProvider(key, model) if key and model else UnconfiguredProvider()
