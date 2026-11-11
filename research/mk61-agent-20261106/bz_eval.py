"""A/B uses one short runtime prompt, either gold or the real BU1500 translator."""
import time
from bz_common import ROOT,rows
from bz_runtime import Session
from bj_runtime import render
from ay_runtime import goal_state
from ay_codec import encode
from by_eval import oracle_generation
from bw_eval import Cache,replan_metrics
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base


def evaluate(actor,translator,tok,split,mode,policy,progress,cache):
    assert mode in ['gold','own'];install();vm=CachedVM();goals=rows(ROOT/(split+'.jsonl'))
    initial={render(goal_state(g),'spec'):g for g in goals};replans={};phase='initial';calls=[]
    assert len(initial)==len(goals)
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)

    class RoutedSession(Session):
        def __init__(self,goal,*args,**kwargs):
            self.source_goal=goal;super().__init__(goal,*args,**kwargs)
            if mode=='gold':assert self.declared_spec==goal['spec']
        def replan_request(self):
            p=super().replan_request()
            if p in replans:assert replans[p]['spec']==self.source_goal['spec'] and replans[p]['pool']==self.pool
            replans[p]=self.source_goal;return p
        def apply_replan(self,body):
            before=list(self.body)
            if mode=='gold':assert body==encode(self.source_goal['spec'],self.pool)
            super().apply_replan(body);assert self.body==before
            if mode=='gold':assert self.declared_spec==self.source_goal['spec']

    def generate(m,t,prompts,forced_action=None):
        output=[]
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            started=time.monotonic()
            if forced_action=='write':
                lookup=initial if phase=='initial'else replans;assert p in lookup
                if mode=='gold':g=oracle_generation(t,p,lookup[p],'initial'if phase=='initial'else'replan')
                else:
                    g=cache.generate('translator',translator,t,p,'write')
                    g.update(profile='translator',phase='initial'if phase=='initial'else'replan',answer_supplied=False,model_inference=True)
            else:
                assert phase=='runtime' and forced_action is None
                g=cache.generate('actor',actor,t,p,None)
                g.update(profile='actor',phase='actor',answer_supplied=False,model_inference=True)
            if g['model_inference']:duty(started,policy)
            output.append(g);calls.append({k:g[k]for k in ['profile','phase','input_tokens','codec_error','seconds','cache_hit','model_inference']if k in g})
            if len(calls)%100==0:progress('inference',split=split,mode=mode,calls=len(calls),cache_hits=sum(v.get('cache_hit',False)for v in calls))
        return output

    try:
        base.Session=RoutedSession;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(actor,tok,goals,'spec',vm);phase='runtime'
        baseline_name='baseline-'+split+'-'+mode+'.json'
        from bz_common import read
        previous=read(ROOT/baseline_name)['primary']['records'];assert len(previous)==len(primary)
        for a,b in zip(previous,primary):
            assert a['id']==b['id'] and a['declared_spec']==b['declared_spec']
            assert a['generation']['generated_token_ids']==b['generation']['generated_token_ids'],'Initial interpretation changed'
        records=base.episodes(actor,tok,goals,{r['id']:r for r in primary},vm,'self')
        for r in records:
            if mode=='gold':assert r['initial_spec']==r['declared_spec'] and r['final_spec_intent']['tested_equal']
            for h in r['history']:
                g=h.get('generation')
                if not g:continue
                if h['kind']=='replan' or g.get('phase')=='replan':assert g['profile']==('oracle_spec'if mode=='gold'else'translator')
                else:assert g['profile']=='actor'
        return {'split':split,'mode':mode,'format':'compact','optimizer_updates':0,
            'oracle_diagnostic':mode=='gold','independent_solution_score':mode=='own',
            'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
            'own':{'summary':base.metrics(records),'records':records,'replan':replan_metrics(records,goals)},
            'calls':{'count':len(calls),'cache_hits':sum(v.get('cache_hit',False)for v in calls),'records':calls},
            'initial_interpretations_equal_frozen_baseline':True,'context':1024,'KV':'FP32','max_actions':12,
            'routing':'unchanged initial/replan prompts; only ordinary actor request text is compact; all ordinary actions and WRITE bodies still use actor'}
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def selection(reports,parents):
    checks={}
    for mode in ['gold','own']:
        a=reports[mode]['own']['summary'];b=parents[mode]['own']['summary']
        checks[mode+'_more_completions']=a['passed']>=b['passed']+2
        for k in ['wrong_starts_repaired','correct_starts_completed']:checks[mode+'_'+k]=a[k]>=b[k]
        for k in ['false_DONE','correct_starts_corrupted']:checks[mode+'_'+k]=a[k]<=b[k]
    return {'chosen_format':'compact'if all(checks.values())else'original','all_checks_passed':all(checks.values()),
        'checks':checks,'closed_seen':False,'optimizer_updates':0,
        'selection_uses_both_gold_and_own_development':True,'product_profile_modified':False}
