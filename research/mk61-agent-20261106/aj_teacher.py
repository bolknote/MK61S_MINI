"""Budget-aware verified corrections from actual student histories."""
import copy
from af_teacher import correct,make_session as original_session
from ag_teacher import changed_indexes
from aj_common import MAX_TURNS
from ha_protocol import encode,bytes_text


def make_session(t,seed,vm):
    s=original_session(t,seed,vm)
    consumed=seed.get('consume_prefill_actions',0)
    assert 0<=consumed<=seed.get('prefill_revision',0)
    s.initial_history-=consumed
    return s


def expert(s,t):
    if t.get('underspecified'):return 'unsure',[]
    remaining=MAX_TURNS-(len(s.history)-s.initial_history);ok=correct(s.vm,t,s.body,s.pool)
    eligible,missing,failed=s.eligibility()
    if ok:
        if missing:return ('run',[missing[0]])if remaining>=len(missing)+1 else('unsure',[])
        if eligible:return 'done',[]
        return ('trace',[])if not s.trace_seen()and remaining>1 else('unsure',[])
    if remaining<=1:return 'unsure',[]
    if s.body is None:return 'write',encode(t['reference_code'],s.pool,'asm')
    if failed and not s.trace_seen():return 'trace',[]
    return 'write',encode(t['reference_code'],s.pool,'asm')


def row(s,t,origin,**extra):
    action,body=expert(s,t);ok=int(correct(s.vm,t,s.body,s.pool))
    r={'task_id':t['id'],'prompt':s.request(),'action':action,'body':body,'correctness':ok,'level':t.get('level',1),
      'group':t.get('group'),'origin':origin,'eligible_for_DONE':s.eligibility()[0],'runtime_has_expected':False,
      'remaining_actions':MAX_TURNS-(len(s.history)-s.initial_history),'loop_exit':bool(ok and action in ['run','done']),**extra}
    if action=='write'and s.body:r['changed_byte_indexes']=changed_indexes(bytes_text(s.body).split(),bytes_text(body).split())
    return r


def fork(s):
    result=copy.copy(s)
    result.__dict__={k:v if k=='vm'else copy.deepcopy(v)for k,v in s.__dict__.items()}
    return result


def follow(s,t,origin='verified_recovery',**extra):
    values=[]
    for _ in range(max(0,MAX_TURNS-(len(s.history)-s.initial_history))):
        r=row(s,t,origin,**extra);values.append(r);kind=s.apply_action(r['action'],r['body'])
        if kind in ['done','unsure']:break
    return values

