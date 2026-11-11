"""Real paired first-action interventions under the unchanged bounded parent policy."""
import copy
import time
import torch
from bw_eval import Cache
from bs_resources import duty,headroom
from aq_protocol import prompt_ids
from cd_common import ACTIONS,ACTION_IDS
from cd_state import make_session
from ar_spec import verify,equivalent

DIAG=ACTIONS.index('diag')
OTHER=[i for i in range(len(ACTIONS))if i!=DIAG]

class Decoder:
    def __init__(self,actor,translator,tok,policy,progress):
        self.actor=actor;self.translator=translator;self.tok=tok;self.policy=policy;self.progress=progress;self.cache=Cache();self.calls=0;self.current_case=None
    def generate(self,profile,prompt,forced=None):
        if self.calls%100==0:headroom(self.policy,self.progress)
        active=time.monotonic();m=self.translator if profile=='translator'else self.actor
        g=self.cache.generate(profile,m,self.tok,prompt,forced);self.calls+=1;duty(active,self.policy)
        g.update(profile=profile,phase='replan'if profile=='translator'else'actor',model_inference=True,answer_supplied=False)
        if self.calls%100==0:self.progress('utility_rollouts',case=self.current_case,model_calls=self.calls,cache_hits=self.cache.hits)
        return g

@torch.inference_mode()
def feature(actor,tok,prompt):
    tokens=prompt_ids(tok,prompt);assert len(tokens)<1016 and not set(tokens)&set(ACTION_IDS)
    ids=torch.tensor([tokens],device=next(actor.parameters()).device)
    h=actor.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state[:,-1].float()
    logits=torch.nn.functional.linear(h,actor.get_input_embeddings().weight[ACTION_IDS]).float()
    return h[0].cpu(),logits[0].cpu()

def rollout(seed,goal,forced,decoder,vm):
    s=make_session(seed,goal,vm);start=len(s.history);review_before=s.replan_count
    before=verify(vm,s.body,s.pool,goal['spec'],goal['audit_inputs'])['status']=='TESTED'
    initial_intent=equivalent(s.declared_spec,goal['spec'],goal['audit_inputs'])['tested_equal'];first=True;wrong_writes=0;first_body=None
    for _ in range(12-start):
        if s.finished or s.abstained or getattr(s,'exhausted',False):break
        if s.pending_runs:
            case=s.pending_runs.pop(0);s.apply_action('run',[case]);s.history[-1]['harness_forced']='missing_public_run';continue
        is_replan=bool(s.pending_replan and not s.replan_attempted)
        if is_replan:s.pending_replan=False;s.replan_attempted=True
        prompt=s.replan_request()if is_replan else s.request()
        force='write'if is_replan else forced if first else None
        generated=decoder.generate('translator'if is_replan else'actor',prompt,force)
        if not is_replan and first:first_body=generated.get('body');first=False
        if generated.get('codec_error'):
            s.history.append({'kind':'generation_error','prompt':prompt,'generation':generated});s.exhausted=True;continue
        try:
            if is_replan:s.apply_replan(generated['body'])
            else:s.apply_action(generated['action'],generated['body'])
        except(ValueError,ArithmeticError,RuntimeError)as error:
            s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
        s.history[-1].update(prompt=prompt,generation=generated)
        if not is_replan and generated['action']=='write'and s.history[-1]['kind']=='write':
            wrong_writes+=verify(vm,s.body,s.pool,goal['spec'],goal['audit_inputs'])['status']!='TESTED'
    s.finalize();correct=verify(vm,s.body,s.pool,goal['spec'],goal['audit_inputs'])['status']=='TESTED'
    claims=[h for h in s.history[start:]if h['kind']in ['done','done_rejected']]
    false_claims=sum(verify(vm,h['evaluated_body'],s.pool,goal['spec'],goal['audit_inputs'])['status']!='TESTED'for h in claims)
    return {'pass':bool(correct and s.finished and s.eligibility()[0]),'finished':s.finished,'program_correct':correct,
        'accepted_false_DONE':bool(s.finished and not correct),'correct_code_at_start':before,'corrupted_after_rollback':bool(before and not correct),
        'wrong_WRITE_actions':wrong_writes,'replans':s.replan_count-review_before,'steps':len(s.history)-start,'prefix_steps':start,
        'abstained':s.abstained,'false_DONE_claims':false_claims,'initial_SPEC_correct':initial_intent,
        'final_SPEC_correct':equivalent(s.declared_spec,goal['spec'],goal['audit_inputs'])['tested_equal'],
        'history':copy.deepcopy(s.history[start:]),'final_body':list(s.body),'forced_first_action':forced,
        'first_generated_body':first_body,'direct_SPEC_request':forced=='diag'and first_body==[4,255,255,0,0]}

def label(review,other):
    # No semantic oracle label replaces the actual outcome of these trials.
    if review['pass']and not other['pass']and review['replans']and review['direct_SPEC_request']:
        return True,'review_enables_success'
    if review['pass']and not other['pass']:return None,'other_diagnosis_not_a_SPEC_review_target'
    if other['pass']and not review['pass']:return False,'review_loses_success'
    if other['pass']and review['pass']:
        safer=review['wrong_WRITE_actions']<other['wrong_WRITE_actions']
        if review['replans']and review['direct_SPEC_request']and safer:return True,'review_prevents_wrong_WRITE'
        return False,'both_succeed_nonreview_preferred'
    if review['corrupted_after_rollback']and other['program_correct']:
        return False,'review_harms_existing_correct_code'
    return None,'neither_trial_demonstrates_a_successful_choice'
