"""Replace only forced interpretation phases; retain the existing actor loop."""
import copy
import time
from by_common import ROOT,rows
from bw_eval import Cache,replan_metrics
from bu_eval import CONFIG
from bj_runtime import Session,render
from ay_runtime import goal_state
from ay_codec import encode,decode as decode_spec
from aq_protocol import prompt_ids,header_ids,decode,ACTION_ID,END
from ha_protocol import bytes_text
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base


def oracle_generation(tok,prompt,goal,phase):
    """The answer is explicitly supplied by the experiment, never by the LM."""
    body=encode(goal['spec'],goal['pool']);assert decode_spec(body,goal['pool'],goal['spec']['angle'])==goal['spec']
    n=len(prompt_ids(tok,prompt));tail=tok.encode(bytes_text(body),add_special_tokens=False)
    values=[ACTION_ID['write'],*tail];assert decode(tok,values)==('write',body)
    overflow=n>=CONFIG['context']-8 or n+len(header_ids(tok,'write'))+len(tail)+1>CONFIG['context'] or len(tail)+1>511
    return {'action':None if overflow else 'write','body':[] if overflow else body,
        'generated_token_ids':[] if overflow else values,'codec_error':'context_overflow' if overflow else None,
        'input_tokens':n,'profile':'oracle_spec','phase':phase,'answer_supplied':True,'model_inference':False,
        'context':CONFIG['context'],'seconds':0.}


def evaluate(actor,tok,split,policy,progress,cache):
    install();vm=CachedVM();goals=rows(ROOT/(split+'.jsonl'));calls=[];phase='initial'
    initial={render(goal_state(g),'spec'):g for g in goals};replans={}
    assert len(initial)==len(goals),'Ambiguous prompt-to-gold routing'
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)

    class OracleSession(Session):
        def __init__(self,goal,*args,**kwargs):
            self.oracle_goal=goal
            super().__init__(goal,*args,**kwargs)
            assert self.declared_spec==goal['spec']
        def replan_request(self):
            prompt=super().replan_request()
            if prompt in replans:assert replans[prompt]['spec']==self.oracle_goal['spec'] and replans[prompt]['pool']==self.pool
            replans[prompt]=self.oracle_goal
            return prompt
        def apply_replan(self,body):
            assert body==encode(self.oracle_goal['spec'],self.pool)
            before=list(self.body);super().apply_replan(body)
            assert self.body==before and self.declared_spec==self.oracle_goal['spec']

    def generate(m,t,prompts,forced_action=None):
        output=[]
        for prompt in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic()
            if forced_action=='write':
                lookup=initial if phase=='initial' else replans
                assert prompt in lookup,'Oracle is available only for a registered interpretation request'
                result=oracle_generation(t,prompt,lookup[prompt],phase)
            else:
                assert phase=='runtime' and forced_action is None
                result=cache.generate('actor',actor,t,prompt,None)
                result.update(profile='actor',phase='actor',answer_supplied=False,model_inference=True)
                duty(start,policy)
            output.append(result)
            calls.append({k:result[k] for k in ['profile','phase','input_tokens','codec_error','seconds','cache_hit','model_inference'] if k in result})
            if len(calls)%100==0:progress('inference',split=split,calls=len(calls),actor_calls=sum(v['model_inference'] for v in calls))
        return output

    try:
        base.Session=OracleSession;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(actor,tok,goals,'spec',vm)
        assert all(r['program_correct'] and r['declared_spec'] is not None for r in primary)
        phase='runtime'
        records=base.episodes(actor,tok,goals,{r['id']:r for r in primary},vm,'self')
        for r in records:
            assert r['initial_spec']==r['declared_spec'] and r['final_spec_intent']['tested_equal']
            for h in r['history']:
                g=h.get('generation')
                if not g:continue
                if h['kind']=='replan':assert g['profile']=='oracle_spec' and not g['model_inference']
                elif g['profile']=='oracle_spec':assert h['kind']=='generation_error' and g['codec_error']=='context_overflow'
                else:assert g['profile']=='actor' and g['model_inference']
        return {'split':split,'oracle_diagnostic':True,'independent_solution_score':False,'optimizer_updates':0,
            'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
            'own':{'summary':base.metrics(records),'records':records,'replan':replan_metrics(records,goals)},
            'calls':{'count':len(calls),'actor_calls':sum(v['model_inference'] for v in calls),
                'actor_cache_hits':sum(v.get('cache_hit',False) for v in calls),'records':calls},
            'routing':'gold only on initial and scheduled code-free replan; every ordinary action and WRITE body uses the immutable Q4 actor',
            'max_actions':12,'context':1024,'KV':'FP32'}
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old
