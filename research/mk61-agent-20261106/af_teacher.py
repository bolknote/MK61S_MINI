"""ROM-verified labels; correct completed code is never rewritten by the expert."""
from ae_teacher import correct,make_session
from af_common import MAX_TURNS
from ha_protocol import encode


def expert(s,t):
    if t.get('underspecified'):return 'unsure',[]
    ok=correct(s.vm,t,s.body,s.pool)
    if len(s.history)-s.initial_history>=MAX_TURNS-1 and not ok:return 'unsure',[]
    if s.body is None:return 'write',encode(t['reference_code'],s.pool,'asm')
    eligible,missing,failed=s.eligibility()
    if ok:
        if missing:return 'run',[missing[0]]
        if eligible:return 'done',[]
        return ('trace',[])if not s.trace_seen()else('unsure',[])
    if failed and not s.trace_seen():return 'trace',[]
    return 'write',encode(t['reference_code'],s.pool,'asm')


def row(s,t,origin,**extra):
    action,body=expert(s,t)
    return {'task_id':t['id'],'prompt':s.request(),'action':action,'body':body,
        'correctness':int(correct(s.vm,t,s.body,s.pool)),
        'level':t.get('level',1),'group':t.get('group'),'origin':origin,
        'eligible_for_DONE':s.eligibility()[0],'runtime_has_expected':False,**extra}


def follow(s,t,origin='targeted_expert'):
    values=[]
    for _ in range(MAX_TURNS):
        r=row(s,t,origin);values.append(r);kind=s.apply_action(r['action'],r['body'])
        if kind in ['done','unsure']:break
    return values

