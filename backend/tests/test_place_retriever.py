"""#22 PlaceRetriever hard filters on [가상] synthetic fixtures (FR-007, FR-008, DEC-015, DEC-023)."""
import json

import pytest

from app.api.profile_models import Profile
from app.application.extraction import blank_profile
from app.courses.fakes import synthetic_source
from app.courses.validator import candidate_violations
from app.data.geo import haversine_m
from app.data.memory import InMemoryPlaceRepository
from app.data.repository import RepositoryError
from app.data.settings import SettingsError
from app.domain.course import CandidateRetriever, CourseSettings
from app.domain.place import AccessibilityRecord, OpenHoursRecord, PlaceRecord, WEEKDAY_KEYS
from app.courses.open_hours import find_slot
from app.retrieval import PlaceRetriever, RetrievalSettings, RetrievalSettingsError, load_retrieval_settings
from app.retrieval.retriever import FIELD_ADDRESS, FIELD_INDOOR, FIELD_OPEN_HOURS

CENTER = (35.159084, 129.160279)
METERS_PER_DEGREE_LAT = 111_195.0
ALL_DAYS = {day: [{'open': '09:00', 'close': '20:00'}] for day in WEEKDAY_KEYS}
# ready window: 2026-11-13 is a Friday, 13:00–18:00 KST
FRI = '2026-11-13'
SOURCE = synthetic_source()
YES = (True, True)


def place(identifier, *, north_m=100.0, category='CAFE', hours=ALL_DAYS, address='[가상] 해운대 테스트 주소',
          access=YES, grade='VERIFIED', indoor=True, stay=60, area='HAEUNDAE'):
    accessibility = None
    if access is not None:
        accessibility = AccessibilityRecord(grade, access[0], access[1], None, None, '[가상] 원문', SOURCE.id)
    return PlaceRecord(SOURCE.code, str(identifier), f'[가상] 장소 {identifier}', category, area, address,
                       CENTER[0] + north_m / METERS_PER_DEGREE_LAT, CENTER[1], indoor,
                       OpenHoursRecord(hours, '[가상] 운영시간 원문'), None, None, None, stay, None,
                       SOURCE.id, '2026-11-19T00:00:00+09:00', accessibility)


def profile(mobility=None, *, start=f'{FRI}T13:00:00+09:00', end=f'{FRI}T18:00:00+09:00',
            excluded=None, indoor=None, indoor_strength='HARD'):
    values = blank_profile()
    values['area'] = {'value': 'HAEUNDAE', 'source': 'USER', 'strength': 'HARD'}
    values['timeWindow'] = {'value': {'startAt': start, 'endAt': end}, 'source': 'USER', 'strength': 'HARD'}
    values['transport'] = {'value': 'WALK', 'source': 'DEFAULT', 'strength': 'HARD'}
    if mobility is not None:
        values['mobility'] = {'value': mobility, 'source': 'USER', 'strength': 'HARD'}
    if excluded is not None:
        values['excludedCategories'] = {'value': excluded, 'source': 'USER', 'strength': 'HARD'}
    if indoor is not None:
        values['indoorPreference'] = {'value': indoor, 'source': 'USER', 'strength': indoor_strength}
    return Profile.model_validate(values)


def settings(**overrides):
    values = {'area_centers': {'HAEUNDAE': CENTER}, 'radius_m': 1500.0, 'max_candidates': 20}
    values.update(overrides)
    return RetrievalSettings(**values)


def retrieve(places, prof=None, **overrides):
    repository = InMemoryPlaceRepository(places, [SOURCE])
    return PlaceRetriever(repository, settings(**overrides)).retrieve(prof or profile())


def ids(result):
    return [candidate.place.id for candidate in result.candidates]


def pid(identifier):
    return f'{SOURCE.code}:{identifier}'


def test_implements_candidate_retriever_protocol():
    retriever: CandidateRetriever = PlaceRetriever(InMemoryPlaceRepository([], [SOURCE]), settings())
    result = retriever.retrieve(profile())
    assert result.candidates == () and result.excluded_unknown_ids == frozenset()


# --- radius -------------------------------------------------------------------------------

def test_radius_boundary_is_inclusive():
    on, beyond = place('on', north_m=1000.0), place('beyond', north_m=1000.5)
    radius = haversine_m(*CENTER, on.latitude, on.longitude)
    result = retrieve([on, beyond], radius_m=radius)
    assert ids(result) == [pid('on')]
    assert result.candidates[0].distance_m == pytest.approx(radius)
    assert result.excluded_unknown_ids == frozenset()  # outside radius is not "unknown"


def test_radius_comes_from_walk_radius_setting(monkeypatch):
    monkeypatch.setenv('BUSANFIT_WALK_RADIUS_M', '800')
    assert load_retrieval_settings().radius_m == 800.0
    monkeypatch.setenv('BUSANFIT_WALK_RADIUS_M', 'far')
    with pytest.raises(SettingsError):
        load_retrieval_settings()
    monkeypatch.delenv('BUSANFIT_WALK_RADIUS_M')
    assert load_retrieval_settings().radius_m == 1500.0


def test_other_area_is_not_a_candidate():
    result = retrieve([place(1), place(2, area='GWANGALLI')])
    assert ids(result) == [pid(1)]


# --- opening hours ------------------------------------------------------------------------

def hours_on(day, *intervals):
    value = {key: [{'open': '09:00', 'close': '20:00'}] for key in WEEKDAY_KEYS if key != day}
    value[day] = [{'open': o, 'close': c} for o, c in intervals]
    return value


@pytest.mark.parametrize('interval, expected', [
    (('17:00', '18:00'), True),    # exactly one stay before the window ends
    (('17:01', '18:00'), False),   # one minute short
    (('12:00', '14:00'), True),    # 13:00–14:00 inside the window
    (('12:00', '13:59'), False),   # 59 minutes inside the window
    (('18:00', '22:00'), False),   # opens when the window ends
    (('09:00', '24:00'), True),
])
def test_opening_interval_must_hold_the_stay_inside_the_window(interval, expected):
    result = retrieve([place('x', hours=hours_on('fri', interval))])
    assert (ids(result) == [pid('x')]) is expected
    assert result.excluded_unknown_ids == frozenset()  # known hours: rejection, not unknown


@pytest.mark.parametrize('start, end, expected', [
    ('13:00:30', '14:00:30', False),   # 60 min wide, but the scheduler starts 13:01 → 14:01 > end
    ('13:00:30', '14:00:59', False),   # still one second short after rounding
    ('13:00:30', '14:01:00', True),    # 13:01–14:01 fits exactly
    ('13:00:00', '14:00:30', True),    # whole-minute start is not rounded
    ('13:59:59', '15:00:00', True),    # 14:00–15:00 fits exactly
])
def test_window_with_seconds_follows_find_slot_rounding(start, end, expected):
    prof = profile(start=f'{FRI}T{start}+09:00', end=f'{FRI}T{end}+09:00')
    result = retrieve([place('sec')], prof)
    assert (ids(result) == [pid('sec')]) is expected
    assert result.excluded_unknown_ids == frozenset()  # known hours: rejection, not unknown
    window = prof.timeWindow.value
    assert (find_slot(place('sec'), window.startAt, window.endAt, 60) is not None) is expected


def test_unplaceable_places_do_not_take_the_top_twenty():
    # 13:00:30–14:00:30: the 20 nearest places need 60 minutes, which find_slot cannot place
    # after rounding the start to 13:01; the farther 30-minute places must still be returned.
    near = [place(f'near{i}', north_m=10.0 + i, stay=60) for i in range(20)]
    far = [place(f'far{i}', north_m=500.0 + i, stay=30) for i in range(5)]
    prof = profile(start=f'{FRI}T13:00:30+09:00', end=f'{FRI}T14:00:30+09:00')
    result = retrieve(near + far, prof)
    assert ids(result) == [pid(f'far{i}') for i in range(5)]
    window = prof.timeWindow.value
    for candidate in result.candidates:
        assert find_slot(candidate.place, window.startAt, window.endAt, candidate.place.default_stay_min)


def test_closed_day_is_rejected_not_unknown():
    result = retrieve([place('closed', hours=hours_on('fri'))])
    assert result.candidates == () and result.excluded_unknown_ids == frozenset()


def test_missing_weekday_is_unknown():
    hours = {key: value for key, value in ALL_DAYS.items() if key != 'fri'}
    result = retrieve([place('nofri', hours=hours)])
    assert result.candidates == ()
    assert result.excluded_unknown_ids == {pid('nofri')}
    assert result.excluded_unknown_fields == {FIELD_OPEN_HOURS}


@pytest.mark.parametrize('fri_close, sat, expected', [
    ('02:00', [], True),        # Friday 18:00→Saturday 02:00 covers 00:30–01:30
    ('01:00', [], False),       # only 30 minutes left after midnight
    ('24:00', [], False),       # ends at midnight
])
def test_overnight_interval_from_previous_day(fri_close, sat, expected):
    hours = dict(ALL_DAYS, fri=[{'open': '18:00', 'close': fri_close}], sat=sat)
    prof = profile(start='2026-11-14T00:30:00+09:00', end='2026-11-14T01:30:00+09:00')
    result = retrieve([place('night', hours=hours)], prof)
    assert (ids(result) == [pid('night')]) is expected
    assert result.excluded_unknown_ids == frozenset()


def test_window_up_to_midnight_with_24_00_close():
    hours = dict(ALL_DAYS, fri=[{'open': '22:00', 'close': '24:00'}])
    prof = profile(start=f'{FRI}T23:00:00+09:00', end='2026-11-14T00:00:00+09:00')
    assert ids(retrieve([place('late', hours=hours)], prof)) == [pid('late')]


def test_null_open_hours_is_excluded_and_reported_never_always_open():
    unparsed = place('text-only', hours=None)
    assert unparsed.open_hours.text  # original text alone is not evidence (DEC-017)
    result = retrieve([unparsed, place('ok')])
    assert ids(result) == [pid('ok')]
    assert result.excluded_unknown_ids == {pid('text-only')}
    assert result.excluded_unknown_fields == {FIELD_OPEN_HOURS}


# --- mobility (DEC-015, DEC-016) ----------------------------------------------------------

@pytest.mark.parametrize('mode, field', [('WHEELCHAIR', 'wheelchair'), ('STROLLER', 'stroller'),
                                         ('INJURY', 'wheelchair')])
@pytest.mark.parametrize('value', [True, False, None])
def test_mobility_is_judged_per_item(mode, field, value):
    access = {'wheelchair': (value, True), 'stroller': (True, value)}[field]
    result = retrieve([place('p', access=access)], profile([mode]))
    if value is True:
        assert ids(result) == [pid('p')] and result.excluded_unknown_ids == frozenset()
    elif value is False:
        assert result.candidates == () and result.excluded_unknown_ids == frozenset()
    else:
        assert result.candidates == ()
        assert result.excluded_unknown_ids == {pid('p')}
        assert result.excluded_unknown_fields == {f'mobility.{field}'}


def test_stroller_only_place_is_not_a_wheelchair_candidate():
    stroller_only = place('s', access=(False, True))  # grade VERIFIED by DEC-026 ③
    assert retrieve([stroller_only], profile(['STROLLER'])).candidates != ()
    assert retrieve([stroller_only], profile(['WHEELCHAIR'])).candidates == ()
    assert retrieve([stroller_only], profile(['INJURY'])).candidates == ()


def test_grade_is_not_used_for_the_decision():
    verified_but_null = place('v', access=(None, None), grade='VERIFIED')
    unknown_but_true = place('u', access=(True, True), grade='UNKNOWN')
    result = retrieve([verified_but_null, unknown_but_true], profile(['WHEELCHAIR']))
    assert ids(result) == [pid('u')]
    assert result.excluded_unknown_ids == {pid('v')}


def test_missing_accessibility_row_is_null_for_every_item():
    result = retrieve([place('none', access=None)], profile(['WHEELCHAIR', 'STROLLER']))
    assert result.candidates == ()
    assert result.excluded_unknown_fields == {'mobility.wheelchair', 'mobility.stroller'}


def test_no_mobility_constraint_does_not_need_accessibility_rows():
    assert ids(retrieve([place('none', access=None)], profile([]))) == [pid('none')]


# --- other hard conditions ----------------------------------------------------------------

def test_excluded_categories():
    result = retrieve([place('cafe'), place('food', category='FOOD')], profile(excluded=['CAFE']))
    assert ids(result) == [pid('food')]


def test_missing_address_is_unknown():
    result = retrieve([place('noaddr', address=None)])
    assert result.candidates == () and result.excluded_unknown_fields == {FIELD_ADDRESS}


def test_hard_indoor_preference():
    places = [place('in', indoor=True), place('out', indoor=False), place('unk', indoor=None)]
    result = retrieve(places, profile(indoor='INDOOR'))
    assert ids(result) == [pid('in')]
    assert result.excluded_unknown_ids == {pid('unk')} and result.excluded_unknown_fields == {FIELD_INDOOR}
    assert len(retrieve(places, profile(indoor='INDOOR', indoor_strength='SOFT')).candidates) == 3


def test_configured_excluded_ids_are_dropped_and_not_counted_as_unknown():
    duty_free = place('dutyfree', category='SHOPPING', hours=None)
    result = retrieve([duty_free, place('shop', category='SHOPPING')], excluded_place_ids=frozenset({pid('dutyfree')}))
    assert ids(result) == [pid('shop')]
    assert result.excluded_unknown_ids == frozenset()


def test_shipped_duty_free_list_is_loaded():
    loaded = load_retrieval_settings()
    assert loaded.area_centers['HAEUNDAE'] == CENTER
    assert len(loaded.excluded_place_ids) == 112
    assert all(value.startswith('tourapi-kor:') for value in loaded.excluded_place_ids)


def write_config(directory, config, **lists):
    if config is not None:
        (directory / 'retrieval.json').write_text(json.dumps(config), encoding='utf-8')
    for name, content in lists.items():
        text = content if isinstance(content, str) else json.dumps(content)
        (directory / f'{name}.json').write_text(text, encoding='utf-8')


def test_missing_retrieval_config_is_an_error_not_no_exclusion(tmp_path):
    with pytest.raises(RetrievalSettingsError, match='not found'):
        load_retrieval_settings(config_dir=tmp_path)


def test_missing_excluded_files_key_is_an_error_not_no_exclusion(tmp_path):
    write_config(tmp_path, {'areaCenters': {}})
    with pytest.raises(RetrievalSettingsError, match='excludedPlaceIdFiles'):
        load_retrieval_settings(config_dir=tmp_path)


@pytest.mark.parametrize('config, lists', [
    ({'excludedPlaceIdFiles': ['missing.json']}, {}),                      # list file absent
    ({'excludedPlaceIdFiles': ['x.json']}, {'x': '{not json'}),            # unreadable JSON
    ({'excludedPlaceIdFiles': ['x.json']}, {'x': {'ids': []}}),            # no placeIds key
    ({'excludedPlaceIdFiles': ['x.json']}, {'x': {'placeIds': 'a:b'}}),    # placeIds not a list
    ({'excludedPlaceIdFiles': 'x.json'}, {'x': {'placeIds': []}}),         # key not a list
    ({'excludedPlaceIdFiles': ['x.json']}, {'x': {'placeIds': ['no-separator']}}),  # malformed ID
])
def test_broken_excluded_id_list_is_a_setting_error(tmp_path, config, lists):
    write_config(tmp_path, config, **lists)
    with pytest.raises(RetrievalSettingsError):
        load_retrieval_settings(config_dir=tmp_path)


def test_explicit_empty_excluded_files_means_no_exclusion(tmp_path):
    write_config(tmp_path, {'excludedPlaceIdFiles': []})
    loaded = load_retrieval_settings(config_dir=tmp_path)
    assert loaded.area_centers == {'HAEUNDAE': CENTER} and loaded.excluded_place_ids == frozenset()


def test_injected_settings_without_exclusions_keep_every_place():
    # [가상] no-exclusion cases inject RetrievalSettings instead of relying on a missing file
    result = retrieve([place('dutyfree', category='SHOPPING'), place('shop', category='SHOPPING')])
    assert sorted(ids(result)) == [pid('dutyfree'), pid('shop')]


def test_area_without_center_is_an_error_not_zero_candidates():
    with pytest.raises(ValueError):
        retrieve([place(1)], area_centers={'SEOMYEON': CENTER})


# --- aggregation, limit, ordering, errors -------------------------------------------------

def test_excluded_unknown_aggregation():
    places = [
        place('h', hours=None),                                     # openHours
        place('hw', hours=None, access=(None, True)),               # openHours + mobility.wheelchair
        place('w', access=(None, True)),                            # mobility.wheelchair
        place('w-closed', access=(None, True), hours=hours_on('fri')),  # confirmed closed → not unknown
        place('w-false', access=(False, None)),                     # confirmed false → not unknown
        place('ok'),
    ]
    result = retrieve(places, profile(['WHEELCHAIR']))
    assert ids(result) == [pid('ok')]
    assert result.excluded_unknown_ids == {pid('h'), pid('hw'), pid('w')}
    assert result.excluded_unknown_fields == {FIELD_OPEN_HOURS, 'mobility.wheelchair'}


def test_at_most_twenty_candidates_nearest_first():
    places = [place(i, north_m=10.0 * (25 - i)) for i in range(25)]  # place 24 is nearest
    result = retrieve(places)
    assert len(result.candidates) == 20
    assert ids(result) == [pid(i) for i in range(24, 4, -1)]
    distances = [candidate.distance_m for candidate in result.candidates]
    assert distances == sorted(distances)


def test_unknown_places_beyond_the_limit_are_still_counted():
    places = [place(i, north_m=10.0 * i) for i in range(20)] + [place('far-unknown', north_m=1400.0, hours=None)]
    result = retrieve(places)
    assert len(result.candidates) == 20 and result.excluded_unknown_ids == {pid('far-unknown')}


def test_repository_error_is_not_zero_candidates():
    repository = InMemoryPlaceRepository([place(1)], [SOURCE], error=RepositoryError('down'))
    with pytest.raises(RepositoryError):
        PlaceRetriever(repository, settings()).retrieve(profile())


# --- every candidate passes the course engine's candidate check ---------------------------

MIXED = [
    place('ok'), place('far', north_m=1499.0), place('beyond', north_m=1600.0),
    place('food', category='FOOD'), place('shop', category='SHOPPING'), place('noaddr', address=None),
    place('null-hours', hours=None), place('closed', hours=hours_on('fri')),
    place('short', hours=hours_on('fri', ('17:30', '18:00'))), place('night', hours=hours_on('fri', ('17:00', '18:00'))),
    place('w-null', access=(None, True)), place('w-false', access=(False, True)), place('s-null', access=(True, None)),
    place('no-row', access=None), place('outdoor', indoor=False), place('indoor-null', indoor=None),
    place('other-area', area='GWANGALLI'), *[place(f'n{i}', north_m=50.0 + i) for i in range(20)],
]


@pytest.mark.parametrize('prof', [
    profile(), profile([]), profile(['WHEELCHAIR']), profile(['STROLLER']), profile(['INJURY']),
    profile(['WHEELCHAIR', 'STROLLER', 'INJURY']), profile(excluded=['CAFE', 'SHOPPING']),
    profile(indoor='INDOOR'), profile(indoor='OUTDOOR'),
    profile(start='2026-11-15T09:00:00+09:00', end='2026-11-15T21:00:00+09:00'),
])
def test_every_candidate_passes_candidate_violations(prof):
    result = retrieve(MIXED, prof)
    assert len(result.candidates) <= 20
    for candidate in result.candidates:
        assert candidate_violations(candidate, prof, CourseSettings()) == ()
