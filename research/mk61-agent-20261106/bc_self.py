"""Live self-check conflicts; no change to the deployed six-action protocol."""
from ba_lessons import wrong_program
from bc_analysis import desired
from ar_spec import verify,infer,equivalent
from ay_codec import compile_spec
from az_runtime import Session

def bad_hypothesis(g,vm):
    body=wrong_program(g,vm,'argument')[0]
    try:hyp=infer(body,g['pool'],g['spec']['angle'])
    except (ValueError,ArithmeticError):hyp=None
    if hyp is not None and not equivalent(hyp,g['spec'],g['checker_inputs']+g['audit_inputs'])['tested_equal']:
        if verify(vm,g['reference_body'],g['pool'],hyp,g['checker_inputs'])['status']!='TESTED':return hyp,body
    expr=['+',g['spec']['X'],{'constant':'10'}];hyp={**g['spec'],'X':expr,'writes':{r:expr for r in g['spec']['writes']}}
    return hyp,compile_spec(hyp,g['pool'])

def rejected_session(g,vm,kind):
    hyp,bad=bad_hypothesis(g,vm)
    if kind=='valid_feedback':s=Session(g,bad,vm,'spec',g['spec'],True)
    else:
        assert kind=='wrong_hypothesis';s=Session(g,g['reference_body'],vm,'spec',hyp,True)
    s.apply_action('done',[])
    return s
