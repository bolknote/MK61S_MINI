"""Reconstruct the exact same public state and rollback history for both trials."""
from bj_runtime import Session

def event(h):
    g=h.get('generation',{})
    return {'kind':h['kind'],'body':h.get('body',[]),'action':g.get('action'),'generated_body':g.get('body',[]),'forced':h.get('harness_forced')}

def make_session(seed,goal,vm):
    s=Session(goal,seed['initial_body'],vm,'spec',seed['initial_spec'],True,start_case=seed.get('start_case'))
    for h in seed['prefix']:
        if h['kind']=='replan':
            s.pending_replan=False;s.replan_attempted=True;s.apply_replan(h['body'])
        elif h.get('forced')=='missing_public_run':
            assert s.pending_runs and s.pending_runs.pop(0)==h['body'][0];s.apply_action('run',h['body'])
        elif h.get('action'):
            try:s.apply_action(h['action'],h['generated_body'])
            except(ValueError,ArithmeticError,RuntimeError)as error:
                s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
        else:raise ValueError(('Unsupported prefix event',h))
    assert not s.finished and not s.abstained and not s.replan_attempted and not s.pending_runs and not s.pending_replan
    assert s.request()==seed['prompt'],'Counterfactual state must equal the saved public prompt'
    assert len(s.history)==len(seed['prefix'])
    return s
