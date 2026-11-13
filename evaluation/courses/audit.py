"""Independent response audit: does not call CourseValidator or its hours logic."""
from datetime import datetime, timedelta, timezone

SEOUL = timezone(timedelta(hours=9))
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def need(condition, code):
    if not condition:
        raise AssertionError(code)


def minute_is_open(place, point):
    parsed = place.open_hours.parsed
    if parsed is None:
        return False
    point = point.astimezone(SEOUL)
    for offset in (0, 1):
        day = point.date() - timedelta(days=offset)
        minute = offset * 1440 + point.hour * 60 + point.minute
        for span in parsed.get(DAYS[day.weekday()], ()):
            opening = sum(int(value) * factor for value, factor in zip(span['open'].split(':'), (60, 1)))
            closing = sum(int(value) * factor for value, factor in zip(span['close'].split(':'), (60, 1)))
            if closing < opening:
                closing += 1440
            if opening <= minute < closing:
                return True
    return False


def audit_response(body, profile, revision, repository, travel, distances, *, radius_meters=1500):
    need(body['status'] == 'SUCCESS', 'expected_success')
    need(profile['transport']['value'] in (None, 'WALK'), 'unsupported_transport_profile')
    need(profile['budget']['value'] is None, 'unsupported_budget_profile')
    need(not profile['includeUnknownAccessibility'], 'unsupported_unknown_accessibility')
    need(profile['preferenceTags']['value'] in (None, []), 'unsupported_tag_profile')
    need(profile['companions']['value'] is None or profile['companions']['strength'] != 'HARD', 'unsupported_companion_hard')
    course = body['course']
    items, legs = course['items'], course['legs']
    need(2 <= len(items) <= 6, 'item_count')
    need(len(legs) == len(items) - 1, 'leg_count')
    need(course['profileRevision'] == revision, 'revision')
    need(len({item['id'] for item in items}) == len(items), 'duplicate_item')
    need(len({item['place']['id'] for item in items}) == len(items), 'duplicate_place')
    need([item['order'] for item in items] == list(range(1, len(items) + 1)), 'order')
    start = datetime.fromisoformat(profile['timeWindow']['value']['startAt'])
    end = datetime.fromisoformat(profile['timeWindow']['value']['endAt'])
    need(course['availableWindow'] == profile['timeWindow']['value'], 'available_window')
    sources = {source['id'] for source in course['sources']}
    need(len(sources) == len(course['sources']) and bool(sources), 'source_inventory')
    mobility = profile['mobility']['value'] or []
    injury = 'INJURY' in mobility
    stay_total = travel_total = waiting_total = 0
    records = []
    unknown_price = {'status': 'UNKNOWN', 'amount': None, 'currency': 'KRW', 'basis': 'UNKNOWN'}
    for item in items:
        place_id = item['place']['id']
        record = repository.get_place(place_id)
        need(record is not None, 'missing_repository_id')
        records.append(record)
        need(item['place']['area'] == record.area == profile['area']['value'], 'area')
        need(item['place']['category'] == record.category, 'category')
        need(record.category not in (profile['excludedCategories']['value'] or []), 'excluded_category')
        need(distances[place_id] <= radius_meters, 'radius')
        need(item['place']['name'] == record.name and item['place']['address'] == record.address, 'place_facts')
        need(item['place']['coordinates'] == {'latitude': record.latitude, 'longitude': record.longitude}, 'coordinates')
        need(set(item['place']['sourceIds']) == set(record.source_ids) and set(record.source_ids) <= sources, 'source_reference')
        need(all(e['sourceId'] in sources for e in item['place']['accessibility']['evidence']), 'evidence_reference')
        a, b = datetime.fromisoformat(item['startAt']), datetime.fromisoformat(item['endAt'])
        need(start <= a < b <= end, 'time_window')
        need(a.second == a.microsecond == b.second == b.microsecond == 0, 'whole_minute_times')
        need((b - a).total_seconds() == item['stayMinutes'] * 60 and item['stayMinutes'] > 0, 'stay_duration')
        # Check each occupied minute against source intervals independently of
        # the scheduler's interval merging and the production validator.
        for minute in range(item['stayMinutes']):
            need(minute_is_open(record, a + timedelta(minutes=minute)), 'opening_hours')
        for mode in mobility:
            field = 'stroller' if mode == 'STROLLER' else 'wheelchair'
            need(getattr(record.accessibility, field, None) is True, 'source_accessibility')
            need(item['place']['accessibility'][field] is True, 'wire_accessibility')
        preference = profile['indoorPreference']
        if preference['strength'] == 'HARD' and preference['value'] in ('INDOOR', 'OUTDOOR'):
            need(record.indoor is (preference['value'] == 'INDOOR'), 'hard_indoor')
        need(item['place']['price'] == unknown_price, 'unknown_place_price')
        need(item['reasonMethod'] == 'TEMPLATE' and item['reason'] and not item['isAnchor'], 'template_scope')
        stay_total += item['stayMinutes']
    for index, leg in enumerate(legs):
        origin, destination = items[index], items[index + 1]
        need(leg['fromItemId'] == origin['id'] and leg['toItemId'] == destination['id'], 'leg_connection')
        need(leg['mode'] == 'WALK' and leg['method'] == 'DISTANCE_ESTIMATE' and leg['isEstimate'] is True, 'travel_method')
        expected = travel.estimate(records[index], records[index + 1], injury=injury)
        need(expected is not None and type(leg['minutes']) is int and leg['minutes'] == expected.minutes, 'travel_evidence')
        if injury:
            need(leg['minutes'] <= 10, 'injury_walk_limit')
        gap = (datetime.fromisoformat(destination['startAt']) - datetime.fromisoformat(origin['endAt'])).total_seconds() / 60
        need(gap >= leg['minutes'], 'overlap')
        waiting_total += gap - leg['minutes']
        travel_total += leg['minutes']
    need(course['startAt'] == items[0]['startAt'] and course['endAt'] == items[-1]['endAt'], 'course_bounds')
    total = (datetime.fromisoformat(course['endAt']) - datetime.fromisoformat(course['startAt'])).total_seconds() / 60
    summary = course['summary']
    need(summary['totalStayMinutes'] == stay_total, 'stay_total')
    need(summary['totalTravelMinutes'] == travel_total, 'travel_total')
    need(summary['totalWaitingMinutes'] == waiting_total, 'waiting_total')
    need(summary['totalMinutes'] == total == stay_total + travel_total + waiting_total, 'total')
    need(summary['estimatedCost'] == unknown_price, 'unknown_total_cost')
    validation = course['validation']
    need(validation['status'] == 'PASSED' and validation['routeAccessibility'] == 'UNVERIFIED', 'validation_scope')
    for name, condition in profile.items():
        if isinstance(condition, dict) and condition.get('strength') == 'HARD' and condition['value'] not in (None, []):
            need(not any(field == name or field.startswith(name + '.') for field in validation['unverifiedFields']), 'unverified_hard')
    need(any(w['code'] == 'ROUTE_ACCESSIBILITY_UNVERIFIED' for w in body['warnings']), 'route_warning')
    return {'items': len(items), 'legs': len(legs), 'hardViolations': 0, 'missingPlaceIds': 0}
