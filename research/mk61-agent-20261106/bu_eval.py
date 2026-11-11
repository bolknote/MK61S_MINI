"""Translator only for forced goal/review WRITE; every ordinary call uses actor."""
import time
from bu_common import ROOT,read,rows
from bt_decode import generate as decode
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base


CONFIG={'context':1024,'KV':'FP32','symbolic':False}


def evaluate(actor,translator,tokenizer,split,policy=None,progress=None):
    install();policy=policy or read(ROOT/'policy.json');goals=rows(ROOT/(split+'.jsonl'));vm=CachedVM();calls=[]
    if split=='closed':assert(ROOT/'preselected.json').exists()
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        output=[];translation=forced_action=='write';chosen=translator if translation else actor
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic();v=decode(chosen,t,[p],CONFIG,forced_action)[0]
            v['profile']='translator'if translation else'unchanged_actor';output.append(v)
            calls.append({k:v[k]for k in ['profile','input_tokens','codec_error','seconds']if k in v});duty(start,policy)
            if progress and len(calls)%100==0:progress('inference',split=split,calls=len(calls))
        return output
    try:
        base.Session=Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(actor,tokenizer,goals,'spec',vm);plans={r['id']:r for r in primary}
        selected=goals
        if split=='development':
            selected=[]
            for family,n in [('composition',40),('unary',8),('binary',8),('constant',8)]:selected.extend([g for g in goals if g['family']==family][:n])
        own=base.episodes(actor,tokenizer,selected,plans,vm,'self')
        stress=[g for g in goals if g['family']=='composition'][:16 if split=='development'else 32]
        wrong=base.episodes(actor,tokenizer,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
        result={'split':split,'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
            'own':{'summary':base.metrics(own),'records':own},'wrong':{'summary':base.metrics(wrong),'records':wrong},
            'routing':'forced initial/replan WRITE -> translator; every ordinary action/body -> immutable actor',
            'context':1024,'weights':'Q4','KV':'FP32'}
        if split=='development':
            v=base.core.primary(actor,tokenizer,rows(ROOT/'retention.jsonl'),'spec',vm)
            result['retention']={'summary':base.core.primary_metrics(v),'records':v}
        result['calls']={'count':len(calls),'max_input_tokens':max(v['input_tokens']for v in calls),
           'decoder_seconds':sum(v.get('seconds',0)for v in calls),'records':calls}
        return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def key(report,baseline):
    a=report['own']['summary'];b=baseline['own']['summary'];p=report['primary'];q=baseline['primary'];r=report['retention'];t=baseline['retention']
    oldgood={v['id']for v in t['records']if v['program_correct']};lost=sum(v['id']in oldgood and not v['program_correct']for v in r['records'])
    comp=lambda x:sum(v['family']=='composition'and v['program_correct']for v in x['records'])
    checks={'composition_gain':comp(p)>=comp(q)+4,'primary_retained':p['summary']['passed']>=q['summary']['passed'],
        'retention':r['summary']['passed']>=t['summary']['passed']and lost<=2,
        'completed':a['passed']>=b['passed'],'repairs':a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
        'correct_finishes':a['correct_starts_completed']>=b['correct_starts_completed'],
        'false_DONE':a['false_DONE']<=b['false_DONE'],'corruption':a['correct_starts_corrupted']<=b['correct_starts_corrupted'],
        'false_claims':a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims'],
        'wrong_SPEC_false_DONE':report['wrong']['summary']['false_DONE']<=baseline['wrong']['summary']['false_DONE']}
    for family in ['unary','binary']:
        checks['keep_'+family]=sum(v['family']==family and v['program_correct']for v in p['records'])>=sum(v['family']==family and v['program_correct']for v in q['records'])
    return [all(checks.values()),comp(p),p['summary']['passed'],a['passed'],a['wrong_starts_repaired'],-a['false_DONE'],-lost],checks


def brief(r):return {k:r[k]['summary']for k in ['primary','own','wrong','retention']if k in r}
