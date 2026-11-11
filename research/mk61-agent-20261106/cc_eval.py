"""Unchanged legacy prompts, BU1500 translator, emulator gate and action budget."""
from cc_common import ROOT,read,rows
from cb_eval import Cache
from bw_eval import replan_metrics
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base
import time

def evaluate(actor,translator,tok,split,policy,progress,cache):
    if split=='closed':assert(ROOT/'preselected.json').exists()
    install();vm=CachedVM();goals=rows(ROOT/(split+'.jsonl'));phase='initial';calls=[]
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        out=[]
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            started=time.monotonic();translation=forced_action=='write'
            g=cache.generate('translator'if translation else'actor',translator if translation else actor,t,p,forced_action)
            g.update(profile='translator'if translation else'actor',actor_role=cache.actor_role,
                phase='initial'if phase=='initial'else'replan'if translation else'actor',model_inference=True,answer_supplied=False)
            calls.append({k:g[k]for k in ['profile','phase','codec_error','cache_hit']if k in g});out.append(g);duty(started,policy)
            if len(calls)%100==0:progress('inference',role=cache.actor_role,split=split,calls=len(calls),cache_hits=sum(v.get('cache_hit',False)for v in calls))
        return out
    try:
        base.Session=Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(actor,tok,goals,'spec',vm)
        identity=[{'id':r['id'],'SPEC':r['declared_spec'],'tokens':r['generation']['generated_token_ids']}for r in primary]
        receipt=ROOT/(split+'-translation-receipt.json')
        if receipt.exists():assert read(receipt)==identity
        else:__import__('cc_common').write(receipt,identity)
        phase='runtime';records=base.episodes(actor,tok,goals,{r['id']:r for r in primary},vm,'self')
        return {'split':split,'actor_role':cache.actor_role,'format':'original','primary':{'summary':base.core.primary_metrics(primary),'records':primary},
            'own':{'summary':base.metrics(records),'records':records,'replan':replan_metrics(records,goals)},'translator_frozen_and_initial_streams_equal':True,
            'context':1024,'KV':'FP32','max_actions':12,'calls':{'count':len(calls),'cache_hits':sum(v.get('cache_hit',False)for v in calls)}}
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old

def select(candidate,parent,working):
    checks={}
    for split in ['development','retention']:
        a=candidate[split]['own']['summary'];p=parent[split]['own']['summary'];w=working[split]['own']['summary']
        for k in ['passed','wrong_starts_repaired','correct_starts_completed']:checks[split+'_'+k]=a[k]>=max(p[k],w[k])
        for k in ['false_DONE','correct_starts_corrupted','episodes_with_false_DONE_claims']:checks[split+'_'+k]=a[k]<=min(p[k],w[k])
        if split=='retention':
            c={r['id']:r for r in candidate[split]['own']['records']}
            for role,reports in [('parent',parent),('working',working)]:
                checks['retention_'+role+'_successes_kept']=all(not r['pass']or c[r['id']]['pass']for r in reports[split]['own']['records'])
    a=candidate['development']['own']['summary'];p=parent['development']['own']['summary']
    checks['observable_development_gain']=a['passed']>=p['passed']+2 or a['false_DONE']<p['false_DONE']or a['correct_starts_corrupted']<p['correct_starts_corrupted']
    return {'eligible':all(checks.values()),'checks':checks,'closed_seen':False,
        'key':[all(checks.values()),a['passed'],a['wrong_starts_repaired'],-a['false_DONE'],-a['correct_starts_corrupted']]}
