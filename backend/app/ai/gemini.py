"""Cancellable Gemini REST adapter; no payloads or provider errors are logged."""
import os
import re
import json
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx

from app.ai.service import AIRequest, ProviderFailure, Purpose


class _NoCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        return False


class GeminiProvider:
    def __init__(self, api_key: str, model: str, *, transport=None):
        if not api_key or not re.fullmatch(r'gemini-[a-zA-Z0-9.-]+', model):
            raise ValueError('Gemini key and valid model name are required')
        self._api_key, self._model, self._transport = api_key, model, transport
        self._client = None
        self._client_loop = None
        self._client_users = 0

    def _new_client(self):
        return httpx.AsyncClient(transport=self._transport, timeout=10,
            follow_redirects=False, trust_env=False, cookies=CookieJar(policy=_NoCookies()))

    @asynccontextmanager
    async def session(self):
        """Share a pool only inside an explicit event-loop-bound lifetime."""
        loop = asyncio.get_running_loop()
        if self._client_loop is None:
            self._client_loop = loop
        elif self._client_loop is not loop:
            raise RuntimeError('provider pool belongs to another event loop')
        self._client_users += 1
        try:
            yield self
        finally:
            self._client_users -= 1
            if self._client_users == 0:
                client = self._client
                self._client = None
                self._client_loop = None
                if client is not None:
                    await client.aclose()

    async def complete(self, request: AIRequest) -> str:
        try:
            return await self._generate(request)
        except httpx.TimeoutException:
            raise TimeoutError('provider timeout') from None
        except httpx.RequestError:
            raise ProviderFailure('NETWORK_ERROR') from None

    async def _generate(self, request: AIRequest) -> str:
        content = request.user_message
        if request.purpose == Purpose.EXPLAIN:
            context = asdict(request.context)
            context.pop('adjustment_items')
            content = json.dumps(context, ensure_ascii=False)
        if request.purpose == Purpose.MODIFY:
            context = asdict(request.context)
            content = json.dumps({'message': request.user_message, 'course': {
                'mobility': context['mobility'], 'adjustment_items': context['adjustment_items']}}, ensure_ascii=False)
        # AIService owns the total per-attempt deadline and the single retry.
        async with self.session():
            # Keep setup inside the attempt's failure/timeout boundary and
            # create no client at app startup or for invalid AIService input.
            if self._client is None:
                self._client = self._new_client()
            client = self._client
            response = await client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent',
                headers={'x-goog-api-key': self._api_key},
                json={
                    'systemInstruction': {'parts': [{'text': request.system_prompt}]},
                    'contents': [{'role': 'user', 'parts': [{'text': content}]}],
                    'generationConfig': {'responseMimeType': 'application/json',
                                         'responseJsonSchema': request.output_schema,
                                         **({'temperature': 0.2} if request.purpose == Purpose.EXPLAIN else {})},
                },
            )
            if response.status_code != 200:
                reason = ('RATE_LIMITED' if response.status_code == 429 else
                          'UPSTREAM_UNAVAILABLE' if response.status_code >= 500 else 'HTTP_ERROR')
                raise ProviderFailure(reason)
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
                raise ProviderFailure('INVALID_RESPONSE') from None


class UnconfiguredProvider:
    async def complete(self, request: AIRequest) -> str:
        raise RuntimeError('provider is not configured')


def configured_provider():
    # Load .env through uvicorn --env-file backend/.env; never read/print keys here.
    key = os.environ.get('GEMINI_API_KEY', '')
    model = os.environ.get('GEMINI_MODEL', '')
    return GeminiProvider(key, model) if key and model else UnconfiguredProvider()
