"""Offline semantic labels and complete repair trajectories on public-only sessions."""
import copy
from ae_common import MAX_TURNS,public_task
from ac_runtime import Session
from ha_protocol import constants,encode,assemble
from full_isa_vm import check_task

_CACHE={}


def correct(vm,task,body,pool):
    if task.get('underspecified'):return False
    try:code=assemble(body,pool,'asm')if body else None
    except (ValueError,ArithmeticError):return False
    if not code:return False
    key=(task['id'],tuple(code))
    if key in _CACHE:return _CACHE[key]
    try:
        ok=check_task(vm,code,task)['pass']
        if ok and task.get('require_subroutine'):
            called=False
            for case in task['public_tests']:
                actual,_=vm.execute(code,case['segments'][0]['inputs'],angle=task['angle'],max_commands=128,max_frames=1024)
                ops={e['opcode']for e in actual['trace']};called|={0x53,0x52}<=ops
            ok=called
        if ok and task.get('required_named_opcodes'):
            from full_isa_protocol import linear_instructions
            ok=set(task['required_named_opcodes'])<={i['opcode']for i in linear_instructions(code)}
    except (ValueError,ArithmeticError,RuntimeError):ok=False
    _CACHE[key]=bool(ok);return bool(ok)


def make_session(task,seed,vm):
    view=public_task(task);view['constants']=seed.get('pool')or task.get('constants')or constants(task['task']);pool=view['constants']
    if 'compiler_generation'in seed:
        s=Session(view,'asm',vm=vm,gate=False);s.initial_history=0;g=seed['compiler_generation']
        if g.get('codec_error')or g.get('action')!='write':
            s.history.append({'kind':'compiler_error','generation':g,'profile':'compiler'});s.exhausted=True
        else:s.apply_action('write',g['body']);s.history[-1].update(generation=g,profile='compiler')
        return s
    current=seed.get('candidate_code',seed.get('initial_code'));rev=seed.get('prefill_revision',0)
    initial=seed.get('initial_code',current)if rev else current
    body=None if seed.get('start_empty')else encode(initial,pool,'asm')
    s=Session(view,'asm',body=body,vm=vm,gate=False)
    if body is not None:
        s.run(0)
        for _ in range(rev):s.apply_action('write',encode(current,pool,'asm'))
        if seed.get('pre_run_all'):
            for i in range(1,len(task['public_tests'])):s.run(i)
        if seed.get('trace_before'):s.apply_action('trace',[])
        if seed.get('error_probe'):
            s.apply_action('write',[0xFF,1,len(pool),0x50])
        if seed.get('critic_warning'):
            s.observation='Проверка кода: необычная последовательность команд. Эта оценка не доказывает ошибку.'
            s.history.append({'kind':'provided_warning','observation':s.observation,'revision':s.revision})
    s.initial_history=len(s.history);return s


def expert(session,task):
    if task.get('underspecified'):return 'unsure',[]
    s=session;ok=correct(s.vm,task,s.body,s.pool)
    if len(s.history)-s.initial_history>=MAX_TURNS-1 and not ok:return 'unsure',[]
    if s.body is None:return 'write',encode(task['reference_code'],s.pool,'asm')
    eligible,missing,failed=s.eligibility()
    if failed and not s.trace_seen():return 'trace',[]
    if missing:return 'run',[missing[0]]
    if ok:return ('done',[])if eligible else('unsure',[])
    return 'write',encode(task['reference_code'],s.pool,'asm')


def row(session,task,origin,**extra):
    action,body=expert(session,task)
    return {'task_id':task['id'],'prompt':session.request(),'action':action,'body':body,
        'correctness':int(correct(session.vm,task,session.body,session.pool)),
        'level':task.get('level',1),'group':task.get('group'),'origin':origin,
        'eligible_for_DONE':session.eligibility()[0],'runtime_has_expected':False,**extra}


def follow(session,task,origin='expert'):
    rows=[]
    for _ in range(MAX_TURNS):
        value=row(session,task,origin);rows.append(value);kind=session.apply_action(value['action'],value['body'])
        if kind in ['done','unsure']:break
    return rows
