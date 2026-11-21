"""Real retriever/provider integration using explicitly synthetic Repository facts."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import runpy

from fastapi.testclient import TestClient
import pytest

from app.application.course_service import CourseService
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.data.memory import InMemoryPlaceRepository
from app.domain.course import CourseSettings
from app.main import create_app
from app.retrieval import PlaceRetriever
from app.travel.walking import create_travel_provider
from test_place_retriever import place, profile, retrieve, settings, SOURCE

audit=runpy.run_path(str(Path(__file__).resolve().parents[2]/'evaluation/courses/audit.py'))['audit_response']


@pytest.mark.parametrize('modes,access,pool', [
    (None,(None,None),False), ([],(None,None),False),
    (['WHEELCHAIR'],(None,True),True), (['STROLLER'],(True,None),True),
    (['INJURY'],(None,True),True), (['WHEELCHAIR','STROLLER'],(None,None),True),
    (['WHEELCHAIR','STROLLER'],(None,False),False),
])
def test_pool_requires_only_missing_requested_accessibility(modes,access,pool):
    candidate=place('unknown',access=access)
    result=retrieve([candidate],profile(modes))
    assert bool(result.unknown_accessibility_candidates) is pool
    if pool:
        assert result.unknown_accessibility_candidates[0].place==candidate
        assert result.unknown_accessibility_candidates[0].distance_m>0
        assert not result.candidates


@pytest.mark.parametrize('failure', ['excluded-id','category','radius','area','address','unknown-hours',
                                    'closed','short-slot','false-access','unknown-indoor','wrong-indoor'])
def test_pool_preserves_every_definite_exclusion_and_other_unknown(failure):
    kwargs={'access':(None,None)}
    profile_kwargs={}
    overrides={}
    if failure=='category':profile_kwargs['excluded']=['CAFE']
    if failure=='radius':kwargs['north_m']=1600
    if failure=='area':kwargs['area']='OTHER'
    if failure=='address':kwargs['address']=None
    if failure=='unknown-hours':kwargs['hours']=None
    if failure=='closed':kwargs['hours']={'fri':[]}
    if failure=='short-slot':kwargs['hours']={'fri':[{'open':'13:00','close':'13:10'}]}
    if failure=='false-access':kwargs['access']=(False,None)
    if failure in ('unknown-indoor','wrong-indoor'):
        kwargs['indoor']=None if failure=='unknown-indoor' else False
        profile_kwargs['indoor']='INDOOR'
    banned=place('banned',**kwargs)
    if failure=='excluded-id':overrides['excluded_place_ids']=frozenset({banned.id})
    eligible=place('eligible',category='PARK',access=(None,None))
    result=retrieve([banned,eligible],profile(['WHEELCHAIR'],**profile_kwargs),**overrides)
    assert [c.place.id for c in result.unknown_accessibility_candidates]==[eligible.id]
    assert banned.id not in {c.place.id for c in result.candidates}


def test_known_and_unknown_pools_are_separate_distance_sorted_and_bounded():
    unknown=[place(str(i),north_m=i*10,access=(None,None)) for i in range(1,31)]
    known=place('known',north_m=500)
    result=retrieve([*reversed(unknown),known],profile(['WHEELCHAIR']),max_candidates=3)
    assert [c.place.id for c in result.candidates]==[known.id]
    assert [c.place.id for c in result.unknown_accessibility_candidates]==[p.id for p in unknown[:3]]
    assert len(result.excluded_unknown_ids)==30


def connected(modes):
    places=[place('known'),place('unknown1',north_m=110,access=(None,None)),
            place('unknown2',north_m=120,access=(None,None))]
    repository=InMemoryPlaceRepository(places,[SOURCE])
    travel=create_travel_provider()
    service=CourseService(PlaceRetriever(repository,settings()),travel,repository,settings=CourseSettings(radius_meters=1500))
    app=create_app(course_service=service,profile_support=ProfileSupport(True,frozenset(INITIAL_FIELDS),True,True))
    value=profile(list(modes)).model_dump(mode='json')
    value['transport']['source']='USER'
    return app,repository,travel,value


def consented_response(client,value):
    sid=client.post('/api/sessions',json={}).json()['sessionId']
    first=client.put(f'/api/sessions/{sid}/profile',json={'profile':value,'expectedProfileRevision':0})
    assert first.status_code==200 and first.json()['status']=='READY',first.text
    denied=client.post('/api/courses',json={'sessionId':sid,'profileRevision':first.json()['profileRevision']}).json()
    assert denied['status']=='INSUFFICIENT_PLACES'
    assert [s['type'] for s in denied['suggestions']]==['INCLUDE_UNKNOWN_ACCESSIBILITY']
    value=first.json()['profile']
    value['includeUnknownAccessibility']=True
    saved=client.put(f'/api/sessions/{sid}/profile',json={'profile':value,'expectedProfileRevision':first.json()['profileRevision']})
    assert saved.status_code==200 and saved.json()['profile']['includeUnknownAccessibility']
    body=client.post('/api/courses',json={'sessionId':sid,'profileRevision':saved.json()['profileRevision']}).json()
    return sid,saved.json(),body


@pytest.mark.parametrize('modes', [('WHEELCHAIR',),('STROLLER',),('INJURY',),('WHEELCHAIR','STROLLER')])
def test_actual_retriever_consent_conditional_and_reset_over_http(modes):
    app,repository,travel,value=connected(modes)
    with TestClient(app) as client:
        sid,saved,body=consented_response(client,value)
        assert body['course']['validation']['status']=='CONDITIONAL'
        audited=audit(body,saved['profile'],saved['profileRevision'],repository,travel,
                      {p.place.id:p.distance_m for p in repository.find_within_radius(35.159084,129.160279,1500)},
                      allow_unknown_accessibility=True)
        assert audited['consentedUnknownPlaces']==(1 if 'INJURY' in modes else 2)
        changed=deepcopy(saved['profile'])
        changed['mobility']['value']=[]
        reset=client.put(f'/api/sessions/{sid}/profile',json={'profile':changed,'expectedProfileRevision':saved['profileRevision']})
        assert reset.status_code==200 and not reset.json()['profile']['includeUnknownAccessibility']


@pytest.mark.parametrize('fault', ['passed','warning-missing','warning-id','wire-true','missing-unverified',
                                  'other-unknown','source-false','no-consent'])
def test_conditional_independent_audit_rejects_false_claims(fault):
    app,repository,travel,value=connected(('WHEELCHAIR',))
    with TestClient(app) as client:
        _,saved,body=consented_response(client,value)
        if fault=='passed':body['course']['validation']['status']='PASSED'
        elif fault=='warning-missing':body['warnings']=[w for w in body['warnings'] if w['code']!='UNKNOWN_ACCESSIBILITY_INCLUDED']
        elif fault=='warning-id':next(w for w in body['warnings'] if w['code']=='UNKNOWN_ACCESSIBILITY_INCLUDED')['placeIds']=[]
        elif fault=='wire-true':
            next(x for x in body['course']['items'] if x['place']['accessibility']['wheelchair'] is None)['place']['accessibility']['wheelchair']=True
        elif fault=='missing-unverified':body['course']['validation']['unverifiedFields'].remove('mobility.wheelchair')
        elif fault=='other-unknown':body['course']['validation']['unverifiedFields'].append('address')
        elif fault=='source-false':
            target=repository.get_place(next(x['place']['id'] for x in body['course']['items'] if x['place']['accessibility']['wheelchair'] is None))
            repository._places[target.id]=replace(target,accessibility=replace(target.accessibility,wheelchair=False))
        else:saved['profile']['includeUnknownAccessibility']=False
        with pytest.raises(AssertionError):
            audit(body,saved['profile'],saved['profileRevision'],repository,travel,
                  {x['place']['id']:100 for x in body['course']['items']},allow_unknown_accessibility=True)
