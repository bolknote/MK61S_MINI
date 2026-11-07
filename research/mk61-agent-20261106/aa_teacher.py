"""Offline expert labels. This module is never called by the runtime."""
import hashlib
from aa_runtime import Session
from ha_protocol import constants, encode, assemble, suffix_patch
from full_isa_vm import check_task


def grade(session, public=False):
    key=(tuple(session.body or []),public)
    cache=getattr(session,'_offline_grade_cache',None)
    if cache is None:cache={};session._offline_grade_cache=cache
    if key in cache:return cache[key]
    try:
        result=bool(session.body and check_task(session.vm, assemble(session.body, session.pool, 'asm'),
                                                session.task, public=public)['pass'])
    except (ValueError, RuntimeError, ArithmeticError):result=False
    cache[key]=result
    return result


def expert(session):
    """Accept semantically equivalent programs, not just the reference bytes."""
    if session.task.get('underspecified'): return 'unsure', [], 'done', 'underspecified'
    correct = grade(session)
    missing = session.eligibility()[1]
    if correct:
        return ('run', [missing[0]], 'done', 'verify') if missing else ('done', [], 'trace', 'done')
    # Cases that already match the task do not justify guessing unseen cases.
    if missing and grade(session, public=True): return 'run', [missing[0]], 'done', 'verify'
    if len(session.history) >= session.max_turns-1: return 'unsure', [], 'done', 'budget'
    wanted = encode(session.task['reference_code'], session.pool, 'asm')
    if session.body is None: return 'write', wanted, 'done', 'write'
    if not session.history and int(hashlib.sha256(session.task['id'].encode()).hexdigest()[:4],16)%3 == 0:
        return 'trace', [], 'done', 'inspect'
    if session.diagnosis is None:
        at = 0
        while at < min(len(wanted),len(session.body)) and wanted[at] == session.body[at]: at += 1
        if at < len(session.body) and at < len(wanted):
            expected, actual = wanted[at], session.body[at]
            cause = 1 if expected in [0x1C,0x1D,0x22,0x31,0x10,0x11,0x12,0x13] else 2 if expected <= 9 else 3 if 0x60 <= expected <= 0x6E else 4
            return 'diag', [cause,expected,actual,at>>8,at&255], 'done', 'diagnose'
    return 'patch', suffix_patch(session.body,wanted), 'done', 'repair'


def lesson(session, origin, tokenizer=None):
    action, body, rejected, bucket = expert(session)
    prompt = session.request()
    row = {'task_id':session.task['id'], 'prompt':prompt, 'action':action, 'body':body,
           'rejected':rejected, 'bucket':bucket, 'origin':origin,
           'reference_in_runtime_feedback':False, 'grader_current_correct':grade(session)}
    if tokenizer is not None:
        from aa_protocol import target_ids
        if len(tokenizer.encode(prompt,add_special_tokens=False))+len(target_ids(tokenizer,action,body)) > 1024:
            return None
    return row


def trajectory(task, seed, vm, tokenizer):
    session = Session(task, 'asm', body=encode(seed['initial_code'], constants(task['task']), 'asm'), vm=vm, gate=False)
    session.run(0)
    if seed.get('pre_run_all'):
        for index in range(1,len(task['public_tests'])): session.run(index)
    rows = []
    for _ in range(session.max_turns):
        row = lesson(session, 'expert_counterfactual', tokenizer)
        if row is not None: rows.append(row)
        action, body, *_ = expert(session)
        kind = session.apply_action(action,body)
        if kind in ['done','unsure']: break
    return rows
