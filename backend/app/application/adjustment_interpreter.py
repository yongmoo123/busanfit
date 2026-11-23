"""AI intent only; single REMOVE fallback. No interpretation ever mutates a profile."""
from dataclasses import dataclass
import re

from app.ai.service import CourseContext, Purpose
from app.api.adjustment_models import AdjustmentIntent
from app.domain.adjustment import ModificationItem


@dataclass(repr=False)
class InterpretedAdjustment:
    intent: AdjustmentIntent
    fallback: bool = False


class AdjustmentInterpreter:
    def __init__(self, ai=None):
        self.ai = ai

    async def interpret(self, message, course, profile, pending=()):
        if pending and pending[0]['op'] == 'EXTEND_STAY' and pending[0].get('minutes') is None:
            amount = re.fullmatch(r'\s*(\d{1,4})\s*분\s*(?:더)?[.!]?\s*', message)
            if amount and 1 <= int(amount[1]) <= 1440:
                return InterpretedAdjustment(AdjustmentIntent.model_validate(
                    {**pending[0], 'minutes': int(amount[1]), 'followUp': list(pending[1:])}))
        if message.strip().rstrip('.!') in ('네', '네 그렇게 해줘', '네 그렇게 해주세요') and pending:
            first, *rest = pending
            intent = AdjustmentIntent.model_validate({**first, 'followUp': rest})
            return InterpretedAdjustment(intent)
        if self.ai is not None:
            context = CourseContext(mobility=tuple(profile.mobility.value or ()),
                adjustment_items=tuple(ModificationItem(item.order, item.place.name, item.place.category,
                    item.place.indoor, item.startAt.isoformat(), item.endAt.isoformat()) for item in course.items))
            result = await self.ai.complete(Purpose.MODIFY, AdjustmentIntent, user_message=message, context=context)
            if result.data is not None:
                return InterpretedAdjustment(result.data)
        match = re.fullmatch(r'\s*(\d{1,2})번\s*(?:빼\s*(?:줘|주세요)|삭제\s*(?:해줘|해주세요)|제거\s*(?:해줘|해주세요))[.!]?\s*', message)
        intent = AdjustmentIntent(op='REMOVE', targets=[int(match[1])]) if match and int(match[1]) > 0 else AdjustmentIntent(op='UNCLEAR', targets=[])
        return InterpretedAdjustment(intent, fallback=True)
