"""Fresh audit plus explicitly retired repair/retention/composition fit controls."""
import copy
import collections
import time
from bv_common import ROOT,read,rows
from bu_eval import CONFIG
from bt_decode import generate as decode
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import headroom,duty
import bj_eval as base


class ActorCache:
    def __init__(self):self.values={};self.hits=0;self.misses=0;self.actor_id=None;self.tokenizer_id=None
    def generate(self,model,tokenizer,prompt):
        if self.actor_id is None:self.actor_id=id(model);self.tokenizer_id=id(tokenizer)
        assert self.actor_id==id(model)and self.tokenizer_id==id(tokenizer),'Cache belongs to one immutable actor and tokenizer'
        if prompt in self.values:
            self.hits+=1;r=copy.deepcopy(self.values[prompt]);r['actor_cache_hit']=True;r['seconds']=0.;return r
        self.misses+=1;r=decode(model,tokenizer,[prompt],CONFIG)[0];self.values[prompt]=copy.deepcopy(r);r['actor_cache_hit']=False;return r


def evaluate(actor,translator,tokenizer,split,policy=None,progress=None,cache=None,tools=True):
    install();policy=policy or read(ROOT/'policy.json');vm=CachedVM();calls=[]
    if split=='closed':assert(ROOT/'preselected.json').exists()
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        output=[];translation=forced_action=='write'
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic()
            if not translation and cache is not None:v=cache.generate(actor,t,p)
            else:v=decode(translator if translation else actor,t,[p],CONFIG,forced_action)[0]
            v['profile']='translator'if translation else'unchanged_actor';output.append(v)
            calls.append({k:v[k]for k in ['profile','input_tokens','codec_error','seconds','actor_cache_hit']if k in v});duty(start,policy)
            if progress and len(calls)%100==0:progress('inference',split=split,calls=len(calls))
        return output
    try:
        base.Session=Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        if split=='fit':
            result={'split':'fit','fit_controls_not_independent':True}
            for name,file in [('hard','hard.jsonl'),('retention','retention.jsonl'),('composition','composition-regression.jsonl')]:
                values=base.core.primary(actor,tokenizer,rows(ROOT/file),'spec',vm)
                result[name]={'summary':base.core.primary_metrics(values),'records':values}
        else:
            goals=rows(ROOT/(split+'.jsonl'));primary=base.core.primary(actor,tokenizer,goals,'spec',vm);result={'split':split,'primary':{'summary':base.core.primary_metrics(primary),'records':primary}}
            if tools:
                plans={r['id']:r for r in primary};values=base.episodes(actor,tokenizer,goals,plans,vm,'self')
                result['own']={'summary':base.metrics(values),'records':values}
                stress=[g for g in goals if g['family']=='composition'][:16 if split=='development'else 32]
                values=base.episodes(actor,tokenizer,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
                result['wrong']={'summary':base.metrics(values),'records':values}
        result['calls']={'count':len(calls),'decoder_seconds':sum(v.get('seconds',0)for v in calls),
            'actor_cache_hits':sum(v.get('actor_cache_hit',False)for v in calls),'records':calls};return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def fit_key(report,parent):
    hard=report['hard']['records'];p={r['id']:r for r in parent['retention']['records']};q={r['id']:r for r in parent['composition']['records']}
    lost_old=sum(p[r['id']]['program_correct']and not r['program_correct']for r in report['retention']['records'])
    lost_comp=sum(q[r['id']]['program_correct']and not r['program_correct']for r in report['composition']['records'])
    checks={'nine_restored':all(r['program_correct']for r in hard[:9]),'cosine_restored':hard[9]['program_correct'],
        'all_parent_retention_kept':lost_old==0,'all_parent_compositions_kept':lost_comp==0}
    score=[all(checks.values()),sum(r['program_correct']for r in hard[:9]),-lost_comp,-lost_old,report['composition']['summary']['passed']]
    return score,checks


def protected(report,parent):
    a=report['own']['summary'];b=parent['own']['summary']
    checks={'new_SPEC_retained':report['primary']['summary']['passed']>=parent['primary']['summary']['passed'],
        'completed':a['passed']>=b['passed'],'repairs':a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
        'correct_finishes':a['correct_starts_completed']>=b['correct_starts_completed'],
        'false_DONE':a['false_DONE']<=b['false_DONE'],'corruption':a['correct_starts_corrupted']<=b['correct_starts_corrupted'],
        'false_claims':a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims'],
        'wrong_SPEC_false_DONE':report['wrong']['summary']['false_DONE']<=parent['wrong']['summary']['false_DONE']}
    return checks


def brief(r):return {k:v['summary']for k,v in r.items()if isinstance(v,dict)and'summary'in v}
