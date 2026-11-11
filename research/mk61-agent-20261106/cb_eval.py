"""Fixed translator, explicit review-state control and unchanged 12-action gate."""
import time
from cb_common import ROOT,read,rows
from cb_runtime import session_type
from bj_runtime import render
from bw_eval import Cache as ParentCache,replan_metrics
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base


class Cache(ParentCache):
    actor_role='parent'
    def generate(self,profile,model,tok,prompt,forced):
        return super().generate(profile+(':'+self.actor_role if profile=='actor'else''),model,tok,prompt,forced)


def evaluate(actor,translator,tok,split,format,policy,progress,cache):
    if split=='closed':assert(ROOT/'preselected.json').exists()
    install();vm=CachedVM();goals=rows(ROOT/(split+'.jsonl'));phase='initial';calls=[]
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        out=[]
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic();translation=forced_action=='write'
            g=cache.generate('translator'if translation else'actor',translator if translation else actor,t,p,forced_action)
            g.update(profile='translator'if translation else'actor',actor_role=cache.actor_role,
                phase='initial'if phase=='initial'else'replan'if translation else'actor',model_inference=True,answer_supplied=False)
            duty(start,policy);out.append(g)
            calls.append({k:g[k]for k in ['profile','phase','input_tokens','codec_error','cache_hit']if k in g})
            if len(calls)%100==0:progress('inference',role=cache.actor_role,split=split,format=format,calls=len(calls),cache_hits=sum(v.get('cache_hit',False)for v in calls))
        return out
    try:
        base.Session=session_type(format);base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(actor,tok,goals,'spec',vm)
        receipt=ROOT/(split+'-translation-receipt.json')
        identity=[{'id':r['id'],'SPEC':r['declared_spec'],'tokens':r['generation']['generated_token_ids']}for r in primary]
        if receipt.exists():assert read(receipt)==identity,'Frozen translator changed'
        else:from cb_common import write;write(receipt,identity)
        phase='runtime';records=base.episodes(actor,tok,goals,{r['id']:r for r in primary},vm,'self')
        return {'split':split,'format':format,'actor_role':cache.actor_role,'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
            'own':{'summary':base.metrics(records),'records':records,'replan':replan_metrics(records,goals)},
            'translator_frozen_and_initial_streams_equal':True,'review_availability_visible':format!='original',
            'context':1024,'KV':'FP32','max_actions':12,'calls':{'count':len(calls),'cache_hits':sum(v.get('cache_hit',False)for v in calls)}}
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def select(reports,parents):
    checks={}
    for format in ['original','full','notes']:
        for split in ['development','retention']:
            a=reports[format][split]['own']['summary'];b=parents[format][split]['own']['summary'];prefix=format+'_'+split+'_'
            checks[prefix+'completed']=a['passed']>=b['passed']+(2 if format=='notes'and split=='development'else 0)
            for key in ['wrong_starts_repaired','correct_starts_completed']:checks[prefix+key]=a[key]>=b[key]
            for key in ['false_DONE','correct_starts_corrupted']:checks[prefix+key]=a[key]<=b[key]
            if split=='retention':
                old={r['id']:r for r in parents[format][split]['own']['records']}
                checks[prefix+'parent_successes_kept']=all(not old[r['id']]['pass']or r['pass']for r in reports[format][split]['own']['records'])
    a=reports['notes']['development']['own']['summary'];return {'eligible':all(checks.values()),'checks':checks,
        'key':[all(checks.values()),a['passed'],a['wrong_starts_repaired'],-a['false_DONE'],-a['correct_starts_corrupted']],
        'closed_seen':False}
