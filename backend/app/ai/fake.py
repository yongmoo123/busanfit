"""Scripted, network-free test provider. Does not retain received requests."""
import asyncio
from dataclasses import dataclass
from app.ai.service import AIRequest


@dataclass(frozen=True, repr=False)
class FakeReply:
    json_text: str = '{}'
    delay_seconds: float = 0
    fail: bool = False


class FakeProvider:
    def __init__(self, replies: list[FakeReply]):
        self._replies = list(replies)
        self.calls = 0
        self.cancelled = 0

    async def complete(self, request: AIRequest) -> str:
        self.calls += 1
        if not self._replies:
            raise RuntimeError('fake replies exhausted')
        reply = self._replies.pop(0)
        try:
            await asyncio.sleep(reply.delay_seconds)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        if reply.fail:
            raise RuntimeError('fake provider failure')
        return reply.json_text
