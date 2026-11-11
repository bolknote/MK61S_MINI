"""Same bounded tools and gate; only context/KV/visible-code observation changes."""
import collections
import time
from bt_common import ROOT,rows,read,CONFIGS
from bt_decode import generate as decode
from bt_runtime import SymbolicSession
from bj_runtime import Session,render
from bl_spec import install
from bl_vm import CachedVM
from bs_resources import duty,headroom
import bj_eval as base


def evaluate(model,tokenizer,split,name,policy=None,progress=None):
    install()
    if split=='closed':assert(ROOT/'preselected.json').exists()
    goals=rows(ROOT/(split+'.jsonl'));config=CONFIGS[name];policy=policy or read(ROOT/'policy.json');vm=CachedVM()
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    calls=[]
    def generate(m,t,prompts,forced_action=None):
        result=[]
        for p in prompts:
            if len(calls)%100==0:headroom(policy,progress)
            start=time.monotonic();value=decode(m,t,[p],config,forced_action)[0]
            calls.append({k:value[k]for k in ['input_tokens','cache','seconds','codec_error']if k in value})
            result.append(value);duty(start,policy)
            if progress and len(calls)%100==0:progress('inference',config=name,split=split,calls=len(calls))
        return result
    try:
        base.Session=SymbolicSession if config['symbolic']else Session;base.generate=generate;base.core.generate=generate;base.core.render=render
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(model,tokenizer,goals,'spec',vm);plans={r['id']:r for r in primary}
        own=base.episodes(model,tokenizer,goals,plans,vm,'self')
        stress=[g for g in goals if g['family']=='composition'][:16 if split=='diagnostic'else 32]
        wrong=base.episodes(model,tokenizer,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
        gold=base.episodes(model,tokenizer,stress,{g['id']:{'declared_spec':g['spec']}for g in stress},vm,'self')
        return {'split':split,'config':name,'settings':config,'primary':{'summary':base.core.primary_metrics(primary),'records':primary},
           **{k:{'summary':base.metrics(v),'records':v}for k,v in [('own',own),('wrong',wrong),('gold',gold)]},
           'calls':{'count':len(calls),'max_input_tokens':max(r['input_tokens']for r in calls),'max_persistent_KV_bytes':max((r.get('cache',{}).get('bytes',0)for r in calls),default=0),
                    'decoder_seconds':sum(r.get('seconds',0)for r in calls),'KV_expected_capacity_bytes':config['context']*2*10*2*32*(2 if config['KV']=='FP16'else 4),
                    'records':calls},'oracle_modes':['gold','wrong'],'optimizer_updates':0}
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def key(report,baseline):
    a=report['own']['summary'];b=baseline['own']['summary'];w=report['wrong']['summary'];v=baseline['wrong']['summary']
    good={r['id']for r in baseline['primary']['records']if r['program_correct']}
    lost=sum(r['id']in good and not r['program_correct']for r in report['primary']['records'])
    checks={'completion':a['passed']>=b['passed'],'repairs':a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
       'correct_starts':a['correct_starts_completed']>=b['correct_starts_completed'],'false_DONE':a['false_DONE']<=b['false_DONE'],
       'corruption':a['correct_starts_corrupted']<=b['correct_starts_corrupted'],'wrong_SPEC_false_DONE':w['false_DONE']<=v['false_DONE'],
       'false_claims':a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims'],
       'first_SPEC':report['primary']['summary']['passed']>=baseline['primary']['summary']['passed']and lost<=1}
    return [all(checks.values()),a['wrong_starts_repaired'],a['passed'],-a['false_DONE'],-a['correct_starts_corrupted'],-w['false_DONE'],-a['episodes_with_false_DONE_claims']],checks


def brief(r):return {'primary':r['primary']['summary'],**{m:r[m]['summary']for m in ['own','wrong','gold']},'calls':{k:v for k,v in r['calls'].items()if k!='records'}}
