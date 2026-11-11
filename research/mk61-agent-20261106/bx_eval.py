"""Unchanged full agent plus an unconditional matched initial/replan panel."""
import copy
import time
from bx_common import ROOT,read,rows
from bw_eval import Cache,replan_metrics
from bu_eval import CONFIG
from bt_decode import generate as decode
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
from ar_spec import equivalent
import bj_eval as base


def paired_summary(first,repeat,goals):
    a={r['id']:r for r in first};byid={g['id']:g for g in goals};out=[]
    for r in repeat:
        p=a[r['id']];g=byid[r['id']]
        out.append({'id':r['id'],'initial_correct':p['program_correct'],'replan_correct':r['program_correct'],
            'semantic_agreement':equivalent(p['declared_spec'],r['declared_spec'],g['audit_inputs'])['tested_equal']})
    return {'total':len(out),'initial_correct':sum(r['initial_correct']for r in out),'replan_correct':sum(r['replan_correct']for r in out),
        'both_correct':sum(r['initial_correct']and r['replan_correct']for r in out),
        'correct_to_wrong':sum(r['initial_correct']and not r['replan_correct']for r in out),
        'wrong_to_correct':sum(not r['initial_correct']and r['replan_correct']for r in out),
        'semantic_agreement':sum(r['semantic_agreement']for r in out)}


def evaluate(actor,translator,tok,split,policy,progress,cache):
    install();vm=CachedVM();calls=[];phase='initial'
    if split=='closed':assert(ROOT/'preselected.json').exists()
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        explicit='initial'if phase=='initial'else'replan'if forced_action=='write'else'actor'
        assert(forced_action=='write')==(explicit!='actor');output=[]
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            started=time.monotonic()
            if explicit=='actor':g=cache.generate('actor',actor,t,p,None)
            else:g=decode(translator,t,[p],CONFIG,'write')[0]
            g.update(profile='actor'if explicit=='actor'else'translator',phase=explicit);output.append(g)
            calls.append({k:g[k]for k in ['profile','phase','input_tokens','codec_error','seconds','cache_hit']if k in g});duty(started,policy)
            if len(calls)%100==0:progress('inference',split=split,calls=len(calls))
        return output
    def repeated(goals):
        nonlocal phase
        phase='replan'
        def repeat_render(s,arm):
            s=copy.deepcopy(s);s.update(replan=True,remaining=6);return render(s,arm)
        base.core.render=repeat_render
        try:return base.core.primary(actor,tok,goals,'spec',vm)
        finally:base.core.render=render
    try:
        base.Session=Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        if split=='fit':
            result={'split':'fit','retired_training_controls':True}
            for name,file in [('hard','hard.jsonl'),('retention','retention.jsonl'),('composition','composition-regression.jsonl')]:
                phase='initial';g=rows(ROOT/file);v=base.core.primary(actor,tok,g,'spec',vm);result[name]={'summary':base.core.primary_metrics(v),'records':v}
            v=repeated(rows(ROOT/'hard.jsonl'));result['hard_replan']={'summary':base.core.primary_metrics(v),'records':v}
        else:
            goals=rows(ROOT/(split+'.jsonl'));primary=base.core.primary(actor,tok,goals,'spec',vm)
            repeated_values=repeated(goals)
            result={'split':split,'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
                'paired':{'summary':paired_summary(primary,repeated_values,goals),'records':repeated_values,'remaining':6}}
            phase='runtime';v=base.episodes(actor,tok,goals,{r['id']:r for r in primary},vm,'self')
            result['own']={'summary':base.metrics(v),'records':v,'replan':replan_metrics(v,goals)}
            stress=[g for g in goals if g['family']=='composition'][:16 if split=='development'else 32]
            v=base.episodes(actor,tok,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
            result['wrong']={'summary':base.metrics(v),'records':v,'replan':replan_metrics(v,stress)}
        result['calls']={'count':len(calls),'actor_cache_hits':sum(r.get('cache_hit',False)for r in calls)}
        return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def composition_count(r):return sum(x['family']=='composition'and x['program_correct']for x in r['primary']['records'])


def selection(r,fit,parent,parent_fit):
    a=r['own']['summary'];b=parent['own']['summary'];p=r['paired']['summary'];q=parent['paired']['summary']
    checks={'nine_and_cosine_initial':all(x['program_correct']for x in fit['hard']['records']),
        'nine_and_cosine_replan':all(x['program_correct']for x in fit['hard_replan']['records'])}
    for panel in ['retention','composition']:
        old={x['id']:x for x in parent_fit[panel]['records']}
        checks['all_parent_'+panel+'_kept']=not any(old[x['id']]['program_correct']and not x['program_correct']for x in fit[panel]['records'])
    checks.update(SPEC=r['primary']['summary']['passed']>=parent['primary']['summary']['passed'],compositions=composition_count(r)>=composition_count(parent),
        completed=a['passed']>=b['passed']+2,repairs=a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
        correct_finishes=a['correct_starts_completed']>=b['correct_starts_completed'],false_DONE=a['false_DONE']<=b['false_DONE'],
        corruption=a['correct_starts_corrupted']<=b['correct_starts_corrupted'],false_claim_episodes=a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims'],
        wrong_SPEC_false_DONE=r['wrong']['summary']['false_DONE']<=parent['wrong']['summary']['false_DONE'],
        paired_both_correct=p['both_correct']>=q['both_correct'],paired_correct_to_wrong=p['correct_to_wrong']<=q['correct_to_wrong'])
    return {'passed':all(checks.values()),'checks':checks,'key':[all(checks.values()),a['passed'],a['wrong_starts_repaired'],-a['false_DONE'],-a['correct_starts_corrupted'],p['both_correct'],-p['correct_to_wrong']], 'closed_seen':False}


def brief(r):return {k:v['summary']for k,v in r.items()if isinstance(v,dict)and'summary'in v}
