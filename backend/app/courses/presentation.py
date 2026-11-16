"""DB facts -> existing wire contract; conservative deterministic explanations."""
from datetime import datetime, timezone
from uuid import uuid4

from app.api.course_models import Course

# Re-export for existing course callers; both APIs share the same conversion.
from app.places.presentation import UNKNOWN_PRICE, place_payload, source_payloads, warning


def build_course(plan, profile, revision, repository, checked_fields, *, now=None):
    items = []
    source_ids = []
    for index, visit in enumerate(plan.visits, 1):
        source_ids.extend(visit.place.source_ids)
        items.append({'id': f'item-{index:02d}', 'order': index, 'place': place_payload(visit.place),
                      'startAt': visit.start_at.isoformat(), 'endAt': visit.end_at.isoformat(),
                      'stayMinutes': visit.stay_minutes,
                      'reason': '등록된 장소 정보와 이용 시간대를 기준으로 배치했어요.',
                      'reasonMethod': 'TEMPLATE', 'isAnchor': False})
    source_ids = list(dict.fromkeys(source_ids))
    source_payload = source_payloads(repository, source_ids)
    stay = sum(visit.stay_minutes for visit in plan.visits)
    travel = sum(plan.travel_minutes)
    total_seconds = (plan.visits[-1].end_at - plan.visits[0].start_at).total_seconds()
    if total_seconds % 60:
        raise ValueError('course duration is not whole minutes')
    total = int(total_seconds // 60)
    return Course.model_validate({
        'id': uuid4(), 'profileRevision': revision, 'createdAt': now or datetime.now(timezone.utc),
        'availableWindow': profile.timeWindow.value.model_dump(mode='json'),
        'startAt': plan.visits[0].start_at.isoformat(), 'endAt': plan.visits[-1].end_at.isoformat(),
        'items': items,
        'legs': [{'fromItemId': items[i]['id'], 'toItemId': items[i + 1]['id'],
                  'mode': 'WALK', 'minutes': minutes, 'method': 'DISTANCE_ESTIMATE', 'isEstimate': True}
                 for i, minutes in enumerate(plan.travel_minutes)],
        'summary': {'totalStayMinutes': stay, 'totalTravelMinutes': travel,
                    'totalWaitingMinutes': total - stay - travel, 'totalMinutes': total,
                    'estimatedCost': dict(UNKNOWN_PRICE)},
        'validation': {'status': 'PASSED', 'checkedHardConstraints': list(checked_fields),
                       'unverifiedFields': ['price', 'routeAccessibility'], 'routeAccessibility': 'UNVERIFIED'},
        'sources': source_payload})
