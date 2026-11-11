"""Completion policy for the computer prototype, distinct from diagnostic DONE.

An actor or teacher may propose a spec; it cannot confirm its own interpretation
of the user's request. Confirmation is an out-of-band harness input, never a
field accepted from generated model text. Finite testing remains finite testing.
"""
from ar_spec import verify


def completion(vm, body, pool, declared_spec, checker_inputs, *,
               all_public_cases_current=False, task_spec_confirmed=False):
    check=verify(vm,body,pool,declared_spec,checker_inputs)
    result={'verification':check,'done_allowed':False,'proof':False,
            'request_understanding':'confirmed'if task_spec_confirmed else'unconfirmed'}
    if check['status']!='TESTED':
        result['status']='VERIFICATION_FAILED'if check['status']=='FAIL'else'UNKNOWN'
    elif not task_spec_confirmed:
        result['status']='CODE_TESTED_AGAINST_UNCONFIRMED_SPEC'
    elif not all_public_cases_current:
        result['status']='PUBLIC_RUNS_REQUIRED'
    else:
        result.update(status='TESTED_AGAINST_CONFIRMED_SPEC',done_allowed=True)
    return result


def check():
    from ar_common import ROOT,read,write
    from full_isa_vm import FullVM
    from ar_spec import infer
    vm=FullVM();g=read(ROOT/'goals.json')[2]
    wrong_spec=infer(g['wrong_body'],g['pool'],g['angle'])
    self_consistent=completion(vm,g['wrong_body'],g['pool'],wrong_spec,g['checker_inputs'],all_public_cases_current=True)
    assert self_consistent['verification']['status']=='TESTED'and not self_consistent['done_allowed']
    failed=completion(vm,g['wrong_body'],g['pool'],g['spec'],g['checker_inputs'],all_public_cases_current=True,task_spec_confirmed=True)
    assert not failed['done_allowed']and failed['status']=='VERIFICATION_FAILED'
    missing=completion(vm,g['reference_body'],g['pool'],g['spec'],g['checker_inputs'],task_spec_confirmed=True)
    assert not missing['done_allowed']and missing['status']=='PUBLIC_RUNS_REQUIRED'
    accepted=completion(vm,g['reference_body'],g['pool'],g['spec'],g['checker_inputs'],all_public_cases_current=True,task_spec_confirmed=True)
    assert accepted['done_allowed']and not accepted['proof']
    unknown=completion(vm,g['reference_body'],g['pool'],None,g['checker_inputs'],all_public_cases_current=True)
    assert not unknown['done_allowed']and unknown['status']=='UNKNOWN'
    write(ROOT/'completion-policy-checks.json',{'self_consistent_wrong_intent':self_consistent,
            'wrong_implementation':failed,'missing_public_runs':missing,'confirmed_spec':accepted,'no_spec':unknown})
    print('Completion policy: 5 cases passed')


if __name__=='__main__':check()
