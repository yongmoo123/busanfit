"""Canonical Repository facts -> shared Place/Source contract, without inference."""
from app.domain.place import validate_open_hours

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
    known_hours = record.open_hours.parsed is not None
    if known_hours:
        validate_open_hours(record.open_hours.parsed)
    return {'id': record.id, 'name': record.name, 'category': record.category,
            'area': record.area, 'address': record.address,
            'coordinates': {'latitude': record.latitude, 'longitude': record.longitude},
            'indoor': record.indoor,
            'openHours': {'status': 'KNOWN' if known_hours else 'UNKNOWN',
                          'description': record.open_hours.text or ('정규화된 운영시간 구간 기준' if known_hours else None)},
            'price': dict(UNKNOWN_PRICE), 'defaultStayMinutes': record.default_stay_min,
            'accessibility': {'grade': grade, **values, 'evidence': evidence},
            'sourceIds': list(record.source_ids)}


def source_payloads(repository, source_ids):
    unique = list(dict.fromkeys(source_ids))
    sources = repository.get_sources(unique)
    if {source.id for source in sources} != set(unique) or len(sources) != len(unique):
        raise ValueError('incomplete source references')
    by_id = {source.id: source for source in sources}
    return [{'id': by_id[key].id, 'provider': by_id[key].provider, 'datasetName': by_id[key].dataset_name,
             'url': by_id[key].url, 'license': by_id[key].license, 'baseDate': by_id[key].base_date,
             'retrievedAt': by_id[key].retrieved_at} for key in unique]
