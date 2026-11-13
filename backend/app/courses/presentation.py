"""DB facts -> existing wire contract; conservative deterministic explanations."""
from datetime import datetime, timezone
from uuid import uuid4

from app.api.course_models import Course

UNKNOWN_PRICE = {'status': 'UNKNOWN', 'amount': None, 'currency': 'KRW', 'basis': 'UNKNOWN'}


def warning(code, message, ids=()):
    return {'code': code, 'message': message, 'placeIds': list(ids)}


def place_payload(record):
    access = record.accessibility
    wheelchair = access.wheelchair if access else None
    stroller = access.stroller if access else None
    grade = ('UNKNOWN' if wheelchair is None and stroller is None else
             'UNSUITABLE' if wheelchair is False and stroller is False else
             'VERIFIED' if wheelchair is True or stroller is True else 'UNKNOWN')
    values = {'wheelchair': wheelchair, 'stroller': stroller,
              'elevator': access.elevator if access else None,
              'accessibleToilet': access.accessible_toilet if access else None}
    evidence = [{'field': name, 'sourceId': access.source_id, 'note': '제공된 구조화 접근성 항목 기준입니다.'}
                for name, value in values.items() if value is not None] if access else []
    return {'id': record.id, 'name': record.name, 'category': record.category,
            'area': record.area, 'address': record.address,
            'coordinates': {'latitude': record.latitude, 'longitude': record.longitude},
            'indoor': record.indoor,
            'openHours': {'status': 'KNOWN', 'description': record.open_hours.text or '정규화된 운영시간 구간 기준'},
            'price': dict(UNKNOWN_PRICE), 'defaultStayMinutes': record.default_stay_min,
            'accessibility': {'grade': grade, **values, 'evidence': evidence},
            'sourceIds': list(record.source_ids)}


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
    sources = repository.get_sources(source_ids)
    if {source.id for source in sources} != set(source_ids) or len(sources) != len(source_ids):
        raise ValueError('incomplete source references')
    source_payload = [{'id': source.id, 'provider': source.provider, 'datasetName': source.dataset_name,
                       'url': source.url, 'license': source.license, 'baseDate': source.base_date,
                       'retrievedAt': source.retrieved_at} for source in sources]
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
