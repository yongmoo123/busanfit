"""#30 real-DB audit: injected test app by default; --runtime-app audits ordinary startup."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import runpy
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.api.profile_models import Profile
from app.application.course_connection import prepare_runtime_connection
from app.application.extraction import AIConditionExtractor,blank_profile
from app.application.profile_support import INITIAL_FIELDS,ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.data.geo import haversine_m
from app.main import create_app,create_runtime_app
from audit import audit_response
from database_run import file_sha256,validate_evaluation_scope


def run(output,expected_sha,*,runtime=False):
    if not __debug__:raise ValueError('audit requires Python without -O')
    connection=prepare_runtime_connection()
    validate_evaluation_scope(connection)
    db=connection.repository.path
    if output.resolve()==db.resolve():raise ValueError('output must not overwrite DB')
    before=file_sha256(db)
    if before!=expected_sha.lower():raise ValueError('shared DB SHA mismatch')
    contract=runpy.run_path(str(ROOT/'contracts/validate_contract.py'))
    with TestClient(create_runtime_app()) as ordinary:
        session=ordinary.post('/api/sessions',json={}).json()
        ordinary_enabled=session['capabilities']['supportsUnknownAccessibilityInclusion']
        if runtime:assert ordinary_enabled
        ordinary.delete('/api/sessions/'+session['sessionId'])
    app=create_runtime_app() if runtime else create_app(course_service=connection.service,
        extractor=AIConditionExtractor(AIService(UnconfiguredProvider()),ChatRuleParser()),
        profile_support=ProfileSupport(True,frozenset(INITIAL_FIELDS),True,True))
    rows=[]
    modes=[('WHEELCHAIR',),('STROLLER',),('INJURY',),('WHEELCHAIR','STROLLER')]
    windows=[('13:00','18:00'),('13:00','14:30'),('06:00','08:00')]
    with TestClient(app) as client:
        if runtime:
            actual=app.state.course_connection
            assert actual.repository.path==connection.repository.path
            validate_evaluation_scope(actual)
            connection=actual
        for mode in modes:
            for start,end in windows:
                sid=client.post('/api/sessions',json={}).json()['sessionId']
                row={'mode':list(mode),'window':start+'-'+end}
                try:
                    value=blank_profile()
                    for name,data in {'area':'HAEUNDAE','timeWindow':{'startAt':f'2026-11-21T{start}:00+09:00','endAt':f'2026-11-21T{end}:00+09:00'},'mobility':list(mode)}.items():
                        value[name]={'value':data,'source':'USER','strength':'HARD'}
                    saved=client.put(f'/api/sessions/{sid}/profile',json={'profile':value,'expectedProfileRevision':0})
                    assert saved.status_code==200 and saved.json()['status']=='READY'
                    saved=saved.json()
                    retrieval=connection.service.retriever.retrieve(Profile.model_validate(saved['profile']))
                    assert len(retrieval.unknown_accessibility_candidates)<=20
                    for candidate in retrieval.unknown_accessibility_candidates:
                        assert candidate.place.id not in connection.retrieval_settings.excluded_place_ids
                        assert candidate.place.address and candidate.place.open_hours.parsed is not None
                        assert candidate.distance_m<=1500
                    first=client.post('/api/courses',json={'sessionId':sid,'profileRevision':saved['profileRevision']})
                    assert first.status_code==200
                    first=first.json()
                    contract['check'](first,contract['schemas']['CourseResponse'])
                    has_proposal=any(x['type']=='INCLUDE_UNKNOWN_ACCESSIBILITY' for x in first['suggestions'])
                    assert has_proposal==bool(retrieval.unknown_accessibility_candidates)
                    assert len(first['suggestions'])<=3
                    row.update(pool=len(retrieval.unknown_accessibility_candidates),beforeOutcome=first['status'],proposal=has_proposal)
                    if first['course'] is not None:
                        distances={x['place']['id']:haversine_m(*connection.retrieval_settings.area_centers['HAEUNDAE'],
                            x['place']['coordinates']['latitude'],x['place']['coordinates']['longitude']) for x in first['course']['items']}
                        audit_response(first,saved['profile'],saved['profileRevision'],connection.repository,connection.service.travel_provider,distances)
                    consent=deepcopy(saved['profile'])
                    consent['includeUnknownAccessibility']=True
                    accepted=client.put(f'/api/sessions/{sid}/profile',json={'profile':consent,'expectedProfileRevision':saved['profileRevision']})
                    assert accepted.status_code==200 and accepted.json()['status']=='READY'
                    accepted=accepted.json()
                    assert accepted['profile']['includeUnknownAccessibility']
                    started=perf_counter()
                    result=client.post('/api/courses',json={'sessionId':sid,'profileRevision':accepted['profileRevision']})
                    row['postMs']=(perf_counter()-started)*1000
                    assert result.status_code==200
                    result=result.json()
                    contract['check'](result,contract['schemas']['CourseResponse'])
                    row.update(afterOutcome=result['status'],conditional=False,consentedUnknownPlaces=0)
                    if result['course'] is not None:
                        distances={}
                        for item in result['course']['items']:
                            record=connection.repository.get_place(item['place']['id'])
                            assert record.id not in connection.retrieval_settings.excluded_place_ids
                            assert record.address and record.open_hours.parsed is not None
                            distances[record.id]=haversine_m(*connection.retrieval_settings.area_centers['HAEUNDAE'],record.latitude,record.longitude)
                        audited=audit_response(result,accepted['profile'],accepted['profileRevision'],connection.repository,connection.service.travel_provider,distances,allow_unknown_accessibility=True)
                        row.update(conditional=audited['validationStatus']=='CONDITIONAL',consentedUnknownPlaces=audited['consentedUnknownPlaces'])
                    else:assert result['status']=='INSUFFICIENT_PLACES'
                    retry=client.post('/api/courses',json={'sessionId':sid,'profileRevision':accepted['profileRevision']})
                    assert retry.status_code==200 and retry.json()['status']==result['status']
                    contract['check'](retry.json(),contract['schemas']['CourseResponse'])
                    if result['course'] is not None:
                        assert [x['place']['id'] for x in retry.json()['course']['items']]==[x['place']['id'] for x in result['course']['items']]
                        audit_response(retry.json(),accepted['profile'],accepted['profileRevision'],connection.repository,
                                       connection.service.travel_provider,distances,allow_unknown_accessibility=True)
                    if len(mode)>1:
                        reordered=deepcopy(accepted['profile'])
                        reordered['mobility']['value'].reverse()
                        same=client.put(f'/api/sessions/{sid}/profile',json={'profile':reordered,'expectedProfileRevision':accepted['profileRevision']})
                        assert same.status_code==200 and same.json()['profile']['includeUnknownAccessibility']
                        accepted=same.json()
                    changed=deepcopy(accepted['profile'])
                    changed['mobility']['value']=[]
                    reset=client.put(f'/api/sessions/{sid}/profile',json={'profile':changed,'expectedProfileRevision':accepted['profileRevision']})
                    assert reset.status_code==200 and not reset.json()['profile']['includeUnknownAccessibility']
                    row.update(resetVerified=True,postOnlyRetryVerified=True)
                    rows.append(row)
                finally:client.delete(f'/api/sessions/{sid}')
    assert all(any(row['mode']==list(mode) and row['conditional'] for row in rows) for mode in modes)
    assert file_sha256(db)==before
    report={'runDate':datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'codeRevision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'workingTreeModified':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        'dbSha256':before,'syntheticOnly':False,'testOnlyApp':not runtime,
        'appMode':'runtime' if runtime else 'evaluation','ordinaryInclusionEnabled':ordinary_enabled,
        'allChecksPassed':True,'hardViolations':0,'missingPlaceIds':0,'acceptanceComplete':False,'browserVerified':False,
        'scenarioResults':rows,'conditionalScenarios':sum(row['conditional'] for row in rows)}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('allChecksPassed','conditionalScenarios','hardViolations','ordinaryInclusionEnabled')},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-db-sha256',required=True)
    parser.add_argument('--runtime-app',action='store_true')
    args=parser.parse_args()
    run(args.output,args.expected_db_sha256,runtime=args.runtime_app)
