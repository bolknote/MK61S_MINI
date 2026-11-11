"""Offline outcome labels. The runtime never imports this teacher."""
import json
from ac_common import MAX_TURNS
from ac_runtime import Session
from ha_protocol import constants,encode,assemble
from full_isa_vm import check_task

_GRADES={}


def grade(session):
    if session.task.get('underspecified'):return False
    key=(session.task['id'],tuple(session.body or []))
    if key in _GRADES:return _GRADES[key]
    try:result=bool(session.body and check_task(session.vm,assemble(session.body,session.pool,'asm'),session.task)['pass'])
    except (ValueError,RuntimeError,ArithmeticError):result=False
    _GRADES[key]=result;return result


def make_session(task,seed,vm):
    pool=task.get('constants')or constants(task['task'])
    current=seed.get('candidate_code',seed['initial_code'])
    initial=seed['initial_code']if seed.get('prefill_revision',0)else current
    s=Session(task,'asm',body=encode(initial,pool,'asm'),vm=vm,gate=False)
    s.run(0)
    for _ in range(seed.get('prefill_revision',0)):
        assert s.apply_action('write',encode(current,pool,'asm'))=='write'
    if seed.get('pre_run_all'):
        for i in range(1,len(task['public_tests'])):s.run(i)
    if seed.get('trace_before'):s.apply_action('trace',[])
    s.initial_history=len(s.history)
    return s


def expert(s):
    if s.task.get('underspecified'):return 'unsure',[]
    if len(s.history)-getattr(s,'initial_history',0)>=MAX_TURNS-1 and not grade(s):return 'unsure',[]
    eligible,missing,failed=s.eligibility()
    # TRACE is chosen from an observed execution failure, never a task-ID hash.
    if failed and not s.trace_seen():return 'trace',[]
    if missing:return 'run',[missing[0]]
    if grade(s):return 'done',[]
    return 'write',encode(s.task['reference_code'],s.pool,'asm')


def step_row(s,origin):
    action,body=expert(s)
    return {'task_id':s.task['id'],'prompt':s.request(),'action':action,'body':body,'origin':origin,
            'level':s.task.get('level',1),'grader_current_correct':grade(s),
            'revision':s.revision,'cases':len(s.task['public_tests']),'reference_in_observation':False}


def follow(s):
    rows=[]
    for _ in range(MAX_TURNS):
        row=step_row(s,'expert');rows.append(row)
        kind=s.apply_action(row['action'],row['body'])
        if kind in ['done','unsure']:break
    return rows


def forced_path(task,seed,vm,first=None,end='done'):
    """A whole candidate episode with actual ROM observations between decisions."""
    s=make_session(task,seed,vm);steps=[]
    def act(action,body):
        steps.append({'prompt':s.request(),'action':action,'body':body})
        s.apply_action(action,body)
    if first is not None:act('write',first)
    for index in range(len(task['public_tests'])):
        if index not in s.runs:act('run',[index])
    act(end,[])
    return steps,grade(s)


def preference(task,seed,vm):
    pool=task.get('constants')or constants(task['task']);current=seed.get('candidate_code',seed['initial_code'])
    correct=bool(seed['intentionally_correct'])
    if task.get('underspecified'):
        s=make_session(task,seed,vm)
        return {'task_id':task['id'],'level':task.get('level',1),'chosen':[{'prompt':s.request(),'action':'unsure','body':[]}],
                'rejected':[{'prompt':s.request(),'action':'done','body':[]}],'kind':'underspecified'}
    if not correct:
        chosen,ok=forced_path(task,seed,vm,encode(task['reference_code'],pool,'asm'))
        rejected,bad=forced_path(task,seed,vm,encode(current,pool,'asm'))
        assert ok and not bad
        return {'task_id':task['id'],'level':task.get('level',1),'chosen':chosen,'rejected':rejected,
                'kind':'full_correct_write_vs_failed_write_then_DONE','branches_have_equal_actions_and_run_counts':True}
    chosen,ok=forced_path(task,seed,vm)
    s=make_session(task,seed,vm);rejected=[]
    for _ in range(2):
        rejected.append({'prompt':s.request(),'action':'trace','body':[]});s.apply_action('trace',[])
    rejected.append({'prompt':s.request(),'action':'unsure','body':[]})
    assert ok
    return {'task_id':task['id'],'level':task.get('level',1),'chosen':chosen,'rejected':rejected,'kind':'verified_DONE_vs_unfinished'}
