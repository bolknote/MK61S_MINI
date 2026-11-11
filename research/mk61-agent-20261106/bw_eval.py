"""Explicit phase routing with immutable profiles and exact decoder memoization."""
import copy
import time
from bw_common import ROOT,ROUTES,read,rows
from bu_eval import CONFIG
from bt_decode import generate as decode
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
from ar_spec import equivalent
import bj_eval as base


class Cache:
    def __init__(self):self.values={};self.bindings={};self.hits=0;self.misses=0
    def generate(self,profile,model,tok,prompt,forced):
        binding=(id(model),id(tok))
        if profile not in self.bindings:self.bindings[profile]=binding
        assert self.bindings[profile]==binding
        key=(profile,forced,prompt)
        if key in self.values:
            self.hits+=1;v=copy.deepcopy(self.values[key]);v['cache_hit']=True;v['seconds']=0.;return v
        self.misses+=1;v=decode(model,tok,[prompt],CONFIG,forced)[0]
        self.values[key]=copy.deepcopy(v);v['cache_hit']=False;return v


def replan_metrics(records,goals):
    byid={g['id']:g for g in goals};v={'replanned':0,'correct_to_wrong':0,'wrong_to_correct':0,'correct_to_correct':0,'wrong_to_wrong':0}
    for r in records:
        if not r['replans']:continue
        g=byid[r['task_id']];before=equivalent(r['initial_spec'],g['spec'],g['audit_inputs'])['tested_equal']
        after=r['final_spec_intent']['tested_equal'];v['replanned']+=1
        v[('correct'if before else'wrong')+'_to_'+('correct'if after else'wrong')]+=1
    return v


def evaluate(models,tok,route,split,policy,progress,cache):
    install();assert route in ROUTES
    if split=='closed':assert(ROOT/'preselected.json').exists()
    vm=CachedVM();calls=[];phase='initial';initial,replan=ROUTES[route]
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        explicit_phase='initial'if phase=='initial'else'replan'if forced_action=='write'else'actor'
        profile=initial if explicit_phase=='initial'else replan if explicit_phase=='replan'else'actor'
        assert (forced_action=='write')==(explicit_phase!='actor')
        output=[]
        for prompt in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic();g=cache.generate(profile,models[profile],t,prompt,forced_action)
            g.update(profile=profile,phase=explicit_phase);output.append(g)
            calls.append({k:g[k]for k in ['profile','phase','input_tokens','codec_error','seconds','cache_hit']if k in g});duty(start,policy)
            if len(calls)%100==0:progress('inference',route=route,split=split,calls=len(calls))
        return output
    try:
        base.Session=Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        goals=rows(ROOT/(split+'.jsonl'))
        primary=base.core.primary(models['actor'],tok,goals,'spec',vm)
        result={'route':route,'split':split,'initial_profile':initial,'replan_profile':replan,
            'primary':{'summary':base.core.primary_metrics(primary),'records':primary}}
        phase='runtime';values=base.episodes(models['actor'],tok,goals,{r['id']:r for r in primary},vm,'self')
        result['own']={'summary':base.metrics(values),'records':values,'replan':replan_metrics(values,goals)}
        stress=[g for g in goals if g['family']=='composition'][:16 if split=='development'else 32]
        values=base.episodes(models['actor'],tok,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
        result['wrong']={'summary':base.metrics(values),'records':values,'replan':replan_metrics(values,stress)}
        for panel in ['own','wrong']:
            for r in result[panel]['records']:
                for h in r['history']:
                    g=h.get('generation')
                    if not g:continue
                    expected_phase='replan'if h['kind']=='replan'or g.get('phase')=='replan'else'actor'
                    assert g['phase']==expected_phase
                    assert g['profile']==(replan if expected_phase=='replan'else'actor')
        result['calls']={'count':len(calls),'cache_hits':sum(v['cache_hit']for v in calls),'records':calls}
        return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def composition_count(r):return sum(v['family']=='composition'and v['program_correct']for v in r['primary']['records'])


def select(reports):
    parent=reports['UU'];a=parent['own']['summary'];out={}
    for route,r in reports.items():
        b=r['own']['summary'];checks={
            'SPEC':r['primary']['summary']['passed']>=parent['primary']['summary']['passed'],
            'compositions':composition_count(r)>=composition_count(parent),
            'completed':b['passed']>=a['passed'],'repairs':b['wrong_starts_repaired']>=a['wrong_starts_repaired'],
            'correct_finishes':b['correct_starts_completed']>=a['correct_starts_completed'],
            'false_DONE':b['false_DONE']<=a['false_DONE'],'corruption':b['correct_starts_corrupted']<=a['correct_starts_corrupted'],
            'false_claim_episodes':b['episodes_with_false_DONE_claims']<=a['episodes_with_false_DONE_claims'],
            'wrong_SPEC_false_DONE':r['wrong']['summary']['false_DONE']<=parent['wrong']['summary']['false_DONE']}
        out[route]={'checks':checks,'eligible':all(checks.values()),
            'key':[all(checks.values()),b['passed'],b['wrong_starts_repaired'],b['correct_starts_completed'],-b['false_DONE'],
                -b['correct_starts_corrupted'],-b['episodes_with_false_DONE_claims'],route=='UU',route=='NU']}
    chosen=max(out,key=lambda route:out[route]['key'])
    return {'chosen':chosen,'decisions':out,'closed_seen':False,'optimizer_updates':0}


def paired_primary_checks(reports):
    for left,right in [('UU','UN'),('NU','NN')]:
        a=reports[left]['primary']['records'];b=reports[right]['primary']['records']
        assert len(a)==len(b)
        for x,y in zip(a,b):
            assert x['id']==y['id']and x['declared_spec']==y['declared_spec']
            assert x['generation']['generated_token_ids']==y['generation']['generated_token_ids']
    return True


def brief(r):return {k:{'summary':r[k]['summary'],**({'replan':r[k]['replan']}if'replan'in r[k]else{})}for k in ['primary','own','wrong']}
