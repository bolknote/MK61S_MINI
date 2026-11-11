"""Execute the fixed factorial diagnostic without gradients or task-oracle leakage."""
import collections
import copy
import hashlib
import json
import time
import torch
from transformers import AutoTokenizer
from bd_common import ROOT,MODEL,ARMS,read,write,rows,check_frozen,compact_head,output_ids,sha
from az_runtime import Session
from ay_codec import encode
from ay_common import MAX_TURNS
from ar_spec import verify
from full_isa_vm import FullVM
from ay_eval import episode_metrics
from aq_eval import generate
from native_verify import verify_export


def status(phase,**fields):
    value={'phase':phase,'unix':time.time(),'optimizer_updates':0,**fields}
    write(ROOT/'status.json',value);print(json.dumps(value),flush=True)


def signature(value):
    return {k:value.get(k)for k in ['action','body','codec_error','generated_token_ids']}


class Generator:
    def __init__(self,baseline):
        self.cache={};self.counts=collections.Counter();self.model=None;self.tokenizer=None
        for row in baseline['self']['records']:
            for h in row['history']:
                if 'prompt'not in h or'generation'not in h:continue
                prompt,value=h['prompt'],h['generation']
                if prompt in self.cache:assert signature(self.cache[prompt])==signature(value),'Conflicting baseline cache'
                self.cache[prompt]=copy.deepcopy(value)

    def __call__(self,prompts,cache_only=False):
        missing=list(dict.fromkeys(p for p in prompts if p not in self.cache))
        assert not(cache_only and missing),'Original actor replay diverged from its frozen prompts'
        if missing:
            if self.model is None:
                self.model,receipt=verify_export(MODEL);self.model.cuda().eval()
                self.tokenizer=AutoTokenizer.from_pretrained(MODEL/'hf',local_files_only=True)
                compact_head(self.model,output_ids(self.tokenizer));write(ROOT/'Q4-load-verification.json',receipt)
            values=generate(self.model,self.tokenizer,missing)
            with(ROOT/'new-generations.jsonl').open('a')as stream:
                for p,v in zip(missing,values):
                    self.cache[p]=copy.deepcopy(v);stream.write(json.dumps({'prompt':p,'generation':v},ensure_ascii=False)+'\n')
            self.counts['fresh_unique_Q4_prompts']+=len(missing)
        self.counts['actor_requests']+=len(prompts)
        self.counts['cache_hits']+=sum(p not in missing for p in prompts)
        return [copy.deepcopy(self.cache[p])for p in prompts]


def session(job,goal,vm,arm):
    declared=goal['spec']if arm.startswith('oracle_')else job['own_spec']
    return Session(goal,job['body'],vm,'spec',declared,True)


def record(job,goal,s,arm):
    # The goal oracle and audit bank are used here only, after actions finish.
    task_check=verify(s.vm,s.body,s.pool,goal['spec'],goal['audit_inputs'])
    provided_check=verify(s.vm,s.body,s.pool,s.declared_spec,goal['audit_inputs'])
    correct=task_check['status']=='TESTED';eligible=s.eligibility()[0]
    return {'id':job['id'],'task_id':job['task_id'],'panel':goal['panel'],'family':goal['family'],
        'initial':job['initial'],'initially_correct':job['initially_correct'],'arm':arm,
        'program_correct':correct,'spec_consistent':provided_check['status']=='TESTED',
        'finished':s.finished,'eligible':eligible,'pass':bool(correct and s.finished and eligible),
        'abstained':s.abstained,'body':s.body,'declared_spec':s.declared_spec,
        'own_initial_spec_correct':job['own_spec_correct'],'task_audit':task_check,
        'gate_checks':s.gate_checks,'history':s.history}


def actor(arm,jobs,goals,vm,generator):
    result=[]
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24];sessions=[session(j,goals[j['task_id']],vm,arm)for j in chunk]
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];values=generator(prompts,cache_only=arm=='own_actor')
            for s,p,v in zip(active,prompts,values):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as error:
                    s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        result += [record(j,goals[j['task_id']],s,arm)for j,s in zip(chunk,sessions)]
        status('running',arm=arm,episodes_done=len(result),episodes_total=len(jobs),generations=dict(generator.counts))
    return result


def mechanical(s):
    """Only the supplied hypothesis and the checker's own finite input bank."""
    def act(action,body,reason):
        assert len(s.history)<MAX_TURNS
        result=s.apply_action(action,body);s.history[-1]['controller_reason']=reason;return result
    if s.declared_spec is None:
        act('unsure',[],'SPEC_UNAVAILABLE');return
    try:
        current=verify(s.vm,s.body,s.pool,s.declared_spec,s.checker_inputs)
        if current['status']!='TESTED':
            act('write',encode(s.declared_spec,s.pool),'COMPILE_SUPPLIED_SPEC')
        _,missing,failed=s.eligibility()
        if failed:
            act('unsure',[],'PUBLIC_EXECUTION_FAILED');return
        for index in missing:act('run',[index],'RUN_CURRENT_REVISION_MISSING_CASE')
        if not s.eligibility()[0]:
            act('unsure',[],'PUBLIC_EXECUTION_FAILED');return
        if act('done',[],'REQUEST_MECHANICALLY_GATED_COMPLETION')=='done_rejected':
            act('unsure',[],'SUPPLIED_SPEC_OR_COMPILER_FAILED_CHECK')
    except (ValueError,ArithmeticError,RuntimeError)as error:
        s.controller_error=str(error)
        if not s.finished and not s.abstained:act('unsure',[],'CONTROLLER_ERROR '+str(error))


def deterministic(arm,jobs,goals,vm):
    result=[]
    for j in jobs:
        g=goals[j['task_id']];s=session(j,g,vm,arm);mechanical(s)
        result.append(record(j,g,s,arm))
        if len(result)%32==0:status('running',arm=arm,episodes_done=len(result),episodes_total=len(jobs))
    return result


def replay_check(records,previous):
    assert len(records)==len(previous)
    fields=['id','task_id','initial','initially_correct','program_correct','spec_consistent','finished','eligible','pass','abstained','body','declared_spec','gate_checks']
    for actual,old in zip(records,previous):
        for k in fields:assert actual[k]==old[k],(actual['id'],k)
        assert len(actual['history'])==len(old['history']),actual['id']
        for a,b in zip(actual['history'],old['history']):
            assert a.get('prompt')==b.get('prompt')
            assert signature(a.get('generation',{}))==signature(b.get('generation',{}))
    return {'all_episode_results_and_gate_checks_identical':True,'all_prompts_and_generated_token_streams_identical':True,
        'episodes':len(records),'not_an_independent_model_replication':True}


def main():
    check_frozen();assert not(ROOT/'complete.json').exists()
    goals={g['id']:g for g in rows(ROOT/'groups.jsonl')};jobs=rows(ROOT/'jobs.jsonl');baseline=read(ROOT/'baseline.json')
    generator=Generator(baseline);vm=FullVM();started=time.monotonic();summaries={}
    for arm in ARMS:
        check_frozen();status('running',arm=arm,episodes_done=0,episodes_total=len(jobs))
        values=actor(arm,jobs,goals,vm,generator)if arm.endswith('_actor')else deterministic(arm,jobs,goals,vm)
        summary=episode_metrics(values);summary['false_DONE_fraction']=summary['false_DONE']/summary['DONE']if summary['DONE']else None
        write(ROOT/(arm+'.json'),{'arm':arm,'summary':summary,'records':values,'policy_sha256':sha(ROOT/'policy.json')})
        summaries[arm]=summary
        if arm=='own_actor':write(ROOT/'baseline-replay-verification.json',replay_check(values,baseline['self']['records']))
    check_frozen();write(ROOT/'complete.json',{'complete':True,'optimizer_updates':0,'teacher_calls':0,
        'seconds':time.monotonic()-started,'summaries':summaries,'generations':dict(generator.counts),
        'Q4_weights_unchanged':True,'new_closed_exam':False})
    status('complete',summaries=summaries)


if __name__=='__main__':
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    try:main()
    except BaseException as error:
        status('failed',error=repr(error));raise
