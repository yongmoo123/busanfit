"""FR-015 partial edits. No full regeneration, SQL, made-up places, or constraint relaxation."""
from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import uuid4

from app.api.adjustment_models import AdjustmentChanges, ReplacedItem
from app.api.course_models import Course
from app.courses.presentation import build_course, warning
from app.courses.scheduler import TravelCache
from app.courses.validator import candidate_violations, unknown_accessibility_fields
from app.domain.course import Plan, Visit
from app.domain.place import PlaceCandidate
from app.places.presentation import place_payload

OP_LABELS = {'REMOVE': '장소 빼기', 'REPLACE': '장소 바꾸기', 'EXTEND_STAY': '체류 늘리기',
             'INDOOR': '실내로 바꾸기', 'INCLUDE_UNKNOWN': '정보 없는 장소 포함 확인',
             'PROFILE_CHANGE': '조건 변경', 'UNCLEAR': '추가 수정 확인'}


@dataclass(repr=False)
class AdjustmentOutcome:
    status: str
    course: Course
    metadata: dict
    changes: AdjustmentChanges = field(default_factory=AdjustmentChanges)
    questions: list = field(default_factory=list)
    context: list = field(default_factory=list)


def question(field, message):
    return {'field': 'adjustment.' + field, 'message': message}


class CourseAdjustmentService:
    def __init__(self, course_service):
        self.service = course_service

    def adjust(self, old, profile, revision, capabilities, intent, metadata):
        result = AdjustmentOutcome('NOT_APPLIED', old, {
            'warnings': list(metadata.get('warnings', [])),
            'suggestions': list(metadata.get('suggestions', [])),
            'excludedUnknown': metadata.get('excludedUnknown', {'count': 0, 'fields': []})})

        def ask(field, message):
            result.status = 'NEEDS_INPUT'
            result.questions = [question(field, message)]
            if intent.op in ('REMOVE', 'REPLACE', 'EXTEND_STAY'):
                result.context = [intent.model_dump(mode='json', exclude={'followUp'}),
                                  *(op.model_dump(mode='json') for op in intent.followUp)]
            return result

        def reject(message):
            result.metadata['warnings'].append(warning('ADJUSTMENT_NOT_FEASIBLE', message))
            if intent.followUp:
                result.context = [op.model_dump(mode='json') for op in intent.followUp]
                remaining = ', '.join(OP_LABELS[op.op] for op in intent.followUp)
                result.questions = [question('followUp', '첫 수정은 적용하지 못했어요. 남은 ' + remaining + ' 요청을 진행할까요?')]
            return result

        if intent.op == 'PROFILE_CHANGE':
            if intent.field is None:
                return ask('message', '조건 카드에서 어떤 조건을 바꿀지 확인해 주세요.')
            result.status = 'NEEDS_INPUT'
            field = intent.field
            result.questions = [{'field': 'profile.' + field, 'message': '조건 카드나 조건 채팅에서 변경 후 코스를 다시 생성해 주세요.'}]
            result.metadata['suggestions'] = [{'id': 'adjust-edit-profile', 'type': 'EDIT_PROFILE',
                                              'label': '조건 카드에서 변경', 'field': field}]
            return result
        if intent.op == 'INCLUDE_UNKNOWN':
            result.status = 'NEEDS_INPUT'
            result.questions = [question('message', '정보 없는 장소 포함 확인창에서 명시적으로 수락해 주세요.')]
            if capabilities.supportsUnknownAccessibilityInclusion:
                result.metadata['suggestions'] = [{'id': 'adjust-confirm-unknown', 'type': 'INCLUDE_UNKNOWN_ACCESSIBILITY',
                    'label': '정보 없는 장소 포함 확인', 'field': 'includeUnknownAccessibility'}]
            return result
        if intent.op == 'INDOOR':
            result.metadata['warnings'].append(warning('ADJUSTMENT_NOT_SUPPORTED', '실내 교체는 이번 기본 수정 구현 범위에 포함되지 않았어요.'))
            return result
        if intent.op == 'UNCLEAR':
            return ask('message', '예: 2번 빼줘, 1번 다른 카페로, 3번에 15분 더처럼 말씀해 주세요.')
        by_order = {item.order: item for item in old.items}
        if not intent.targets or any(order not in by_order for order in intent.targets):
            return ask('target', '현재 코스에 있는 장소 번호를 확인해 주세요.')
        if intent.op in ('REPLACE', 'EXTEND_STAY') and len(intent.targets) != 1:
            return ask('target', '한 번에 수정할 장소 한 곳을 선택해 주세요.')
        if intent.op == 'EXTEND_STAY' and intent.minutes is None:
            return ask('minutes', '몇 분 더 머무를까요?')
        selected = {by_order[order].id for order in intent.targets}
        if intent.op == 'REMOVE' and len(old.items) - len(selected) < 2:
            return reject('수정 후에도 장소가 두 곳 이상 있어야 해요. 다른 장소를 선택해 주세요.')

        service = self.service
        retrieval = service.retriever.retrieve(profile)
        allow_unknown = profile.includeUnknownAccessibility and capabilities.supportsUnknownAccessibilityInclusion
        pool = (*retrieval.candidates, *(retrieval.unknown_accessibility_candidates if allow_unknown else ()))
        distances = {hit.place.id: hit.distance_m for hit in pool}
        visits = []
        for item in old.items:
            record = service.repository.get_place(item.place.id)
            if record is None or place_payload(record) != item.place.model_dump(mode='json'):
                return reject('장소 정보가 변경되어 현재 코스를 그대로 수정할 수 없어요. 코스를 다시 생성해 주세요.')
            visits.append(Visit(record, item.startAt, item.endAt, item.stayMinutes))
        travel = TravelCache(service.travel_provider, injury='INJURY' in (profile.mobility.value or ()))

        def validate(candidate_visits):
            legs = []
            for a, b in zip(candidate_visits, candidate_visits[1:]):
                estimate = travel(a.place, b.place)
                if estimate is None:
                    return None, None
                legs.append(estimate.minutes)
            plan = Plan(tuple(candidate_visits), tuple(legs))
            check = service.validator.validate(plan, profile, distances, travel,
                allow_unknown_accessibility=allow_unknown)
            return plan, check

        identities = [item.id for item in old.items]
        if intent.op == 'REMOVE':
            result.changes.removedItemIds = [item.id for item in old.items if item.id in selected]
            visits = [visit for item, visit in zip(old.items, visits) if item.id not in selected]
            identities = [item.id for item in old.items if item.id not in selected]
            # Removing a visit preserves all remaining times; only the connecting leg changes.
        elif intent.op == 'EXTEND_STAY':
            index = next(i for i, item in enumerate(old.items) if item.id in selected)
            delta = timedelta(minutes=intent.minutes)
            visits[index] = replace(visits[index], end_at=visits[index].end_at + delta,
                                    stay_minutes=visits[index].stay_minutes + intent.minutes)
            previous = visits[index]
            for i in range(index + 1, len(visits)):
                estimate = travel(previous.place, visits[i].place)
                if estimate is None:
                    return reject('이동시간을 확인하지 못해 연장할 수 없어요.')
                shift = max(timedelta(), previous.end_at + timedelta(minutes=estimate.minutes) - visits[i].start_at)
                visits[i] = replace(visits[i], start_at=visits[i].start_at + shift, end_at=visits[i].end_at + shift)
                previous = visits[i]
        else:
            index = next(i for i, item in enumerate(old.items) if item.id in selected)
            occupied = {item.place.id for item in old.items}
            found = None
            seen = set()
            for hit in pool[:service.settings.max_candidates * 2]:
                if hit.place.id in seen or hit.place.id in occupied:
                    continue
                seen.add(hit.place.id)
                record = service.repository.get_place(hit.place.id)
                if record is None or record.id != hit.place.id:
                    continue
                if intent.category is not None and record.category != intent.category:
                    continue
                if candidate_violations(PlaceCandidate(record, hit.distance_m), profile, service.settings,
                                        allow_unknown_accessibility=allow_unknown):
                    continue
                attempted = list(visits)
                # User-confirmed scope: same slot AND stay, no other time changes.
                attempted[index] = replace(attempted[index], place=record)
                candidate_plan, check = validate(attempted)
                if check is not None and check.accepted:
                    found = attempted
                    break
            if found is None:
                return reject('현재 방문 시간을 바꾸지 않고 교체할 수 있는 후보가 없어요.')
            visits = found
            new_id = 'item-' + uuid4().hex[:12]
            result.changes.replacedItems = [ReplacedItem(oldItemId=identities[index], newItemId=new_id)]
            identities[index] = new_id
        plan, check = validate(visits)
        if check is None or not check.accepted:
            result.changes = AdjustmentChanges()
            return reject('시간창·영업시간·이동 또는 접근성 조건을 지킬 수 없어 기존 코스를 유지했어요. 조건을 바꾸거나 연장 시간을 줄여 주세요.')
        course = build_course(plan, profile, revision, service.repository, check.checked_fields,
                              unverified_fields=check.unverified_fields)
        old_by_id = {item.id: item for item in old.items}
        for item, identity in zip(course.items, identities):
            item.id = identity
        for i, leg in enumerate(course.legs):
            leg.fromItemId, leg.toItemId = identities[i], identities[i + 1]
        # Keep unchanged visits' reason text; never carry a replaced place's reason forward.
        for item in course.items:
            if item.id in old_by_id and item.stayMinutes == old_by_id[item.id].stayMinutes:
                item.reason, item.reasonMethod = old_by_id[item.id].reason, old_by_id[item.id].reasonMethod
        course = Course.model_validate(course.model_dump(mode='json'))
        final = service.validator.validate(plan, profile, distances, travel, allow_unknown_accessibility=allow_unknown)
        if not final.accepted or final.unverified_fields != check.unverified_fields:
            result.changes = AdjustmentChanges()
            return reject('장소 정보가 변경되어 수정 결과를 적용하지 않았어요.')
        result.status, result.course = 'SUCCESS', course
        result.changes.timeChangedItemIds = [item.id for item in course.items if item.id in old_by_id
            and (item.startAt != old_by_id[item.id].startAt or item.endAt != old_by_id[item.id].endAt)]
        result.metadata['warnings'] = [w for w in result.metadata['warnings'] if w['code'] != 'UNKNOWN_ACCESSIBILITY_INCLUDED']
        unknown_ids = [visit.place.id for visit in plan.visits if unknown_accessibility_fields(visit.place, profile)]
        if unknown_ids:
            result.metadata['warnings'].append(warning('UNKNOWN_ACCESSIBILITY_INCLUDED',
                '접근성 정보를 확인하지 못한 장소가 포함되어 있어요. 방문 전에 확인해 주세요.', unknown_ids))
        excluded = retrieval.excluded_unknown_ids - {visit.place.id for visit in plan.visits}
        result.metadata['excludedUnknown'] = {'count': len(excluded),
            'fields': sorted(retrieval.excluded_unknown_fields) if excluded else []}
        new_orders = {item.id: item.order for item in course.items}
        for op in intent.followUp:
            pending = op.model_dump(mode='json')
            ids = [by_order[order].id for order in op.targets if order in by_order]
            # Display orders change after REMOVE. Bind follow-ups to surviving identities,
            # never silently redirect an original number to a different place.
            pending['targets'] = ([new_orders[identity] for identity in ids]
                if len(ids) == len(op.targets) and all(identity in new_orders for identity in ids) else [])
            result.context.append(pending)
        if result.context:
            remaining = ', '.join(OP_LABELS[op['op']] for op in result.context)
            result.questions = [question('followUp', remaining + '도 진행할까요? 다음 요청은 한 번에 하나씩 적용해요.')]
        return result
