"""Q4-only one-shot synthesis and bounded tool episodes; no runtime task oracle."""
import collections
import copy
import json
import random
import statistics
from ay_common import ROOT,rows,read,MAX_TURNS
from ay_runtime import Session,render,goal_state
from ay_codec import to_program
from ay_lessons import mutant
from aq_eval import generate
from full_isa_vm import FullVM
from ar_spec import verify,infer,equivalent


def primary(model,tokenizer,groups,arm,vm):
    records=[]
    for at in range(0,len(groups),24):
        chunk=groups[at:at+24];prompts=[render(goal_state(g),arm)for g in chunk]
        output=generate(model,tokenizer,prompts,forced_action='write')
        for g,p,v in zip(chunk,prompts,output):
            program=[];spec=None;error=v.get('codec_error')
            if not error:
                try:
                    program,spec=to_program(v['body'],g['pool'],g['spec']['angle'],arm)
                    if spec is None:
                        try:spec=infer(program,g['pool'],g['spec']['angle'])
                        except (ValueError,ArithmeticError):pass
                except (ValueError,ArithmeticError,RuntimeError)as e:error=str(e)
            task_check=verify(vm,program,g['pool'],g['spec'],g['audit_inputs'])
            own_check=verify(vm,program,g['pool'],spec,g['audit_inputs'])
            intent=equivalent(spec,g['spec'],g['audit_inputs'])
            records.append({'id':g['id'],'panel':g['panel'],'family':g['family'],'task':g['task'],
              'program':program,'declared_spec':spec,'generation':v,'codec_error':error,
              'program_correct':task_check['status']=='TESTED','intent':intent,'task_audit':task_check,
              'own_spec_consistency':own_check,'prompt':p})
    return records


def choose_runtime(groups,n,seed):
    rng=random.Random(seed);result=[]
    for panel in ['known','novel']:
        values=[g for g in groups if g['panel']==panel]
        result+=rng.sample(values,min(n//2,len(values)))
    return result


def episodes(model,tokenizer,groups,arm,plans,vm,gate):
    jobs=[]
    for i,g in enumerate(groups):
        kind,bad=mutant(g,vm,['operation','argument','order'][i%3])
        jobs.extend([(g,'correct',g['reference_body']),(g,kind,bad)])
    records=[]
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24];sessions=[]
        for g,label,body in chunk:
            declared=plans[g['id']]['declared_spec']
            sessions.append(Session(g,body,vm,arm,declared,gate=='self'))
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];output=generate(model,tokenizer,prompts)
            for s,p,v in zip(active,prompts,output):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as e:
                    s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        for(g,label,body),s in zip(chunk,sessions):
            check=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs']);correct=check['status']=='TESTED'
            eligible=s.eligibility()[0];spec=plans[g['id']]['declared_spec']
            own=verify(vm,s.body,s.pool,spec,g['audit_inputs'])
            records.append({'id':g['id']+':'+label,'task_id':g['id'],'panel':g['panel'],'family':g['family'],
              'initial':label,'initially_correct':label=='correct','gate':gate,'program_correct':correct,
              'spec_consistent':own['status']=='TESTED','finished':s.finished,'eligible':eligible,
              'pass':bool(correct and s.finished and eligible),'abstained':s.abstained,'body':s.body,
              'task_audit':check,'declared_spec':spec,'gate_checks':s.gate_checks,'history':s.history})
    return records


def primary_metrics(records):
    return {'total':len(records),'passed':sum(r['program_correct']for r in records),
            'spec_available':sum(r['declared_spec']is not None for r in records),
            'intent_correct':sum(r['intent']['tested_equal']for r in records),
            'codec_errors':sum(bool(r['codec_error'])for r in records),
            'mean_output_bytes':statistics.mean(len(r['generation'].get('body',[]))for r in records),
            'mean_generated_tokens':statistics.mean(len(r['generation'].get('generated_token_ids',[]))for r in records),
            'mean_input_tokens':statistics.mean(r['generation']['input_tokens']for r in records)}


def episode_metrics(records):
    good=[r for r in records if r['initially_correct']];bad=[r for r in records if not r['initially_correct']]
    return {'total':len(records),'passed':sum(r['pass']for r in records),'DONE':sum(r['finished']for r in records),
            'false_DONE':sum(r['finished']and not r['program_correct']for r in records),
            'false_DONE_spec':sum(r['finished']and not r['spec_consistent']for r in records),
            'final_correct_code':sum(r['program_correct']for r in records),
            'correct_starts':len(good),'correct_starts_completed':sum(r['pass']for r in good),
            'correct_starts_corrupted':sum(not r['program_correct']for r in good),
            'wrong_starts':len(bad),'wrong_starts_repaired':sum(r['pass']for r in bad),
            'wrong_starts_final_correct':sum(r['program_correct']for r in bad),
            'abstained':sum(r['abstained']for r in records),
            'exhausted':sum(not r['finished']and not r['abstained']for r in records),
            'generation_errors':sum(any(h['kind']=='generation_error'for h in r['history'])for r in records),
            'context_overflows':sum(any(h.get('generation',{}).get('codec_error')=='context_overflow'for h in r['history'])for r in records)}


def evaluate(model,tokenizer,split,arm):
    if split=='closed':assert(ROOT/'preselected.json').exists(),'Closed exam cannot be used for checkpoint selection'
    groups=rows(ROOT/(split+'-clean.jsonl'));vm=FullVM();records=primary(model,tokenizer,groups,arm,vm)
    result={'arm':arm,'split':split,'primary':{'summary':primary_metrics(records),'records':records,
      'panels':{p:primary_metrics([r for r in records if r['panel']==p])for p in ['known','novel']}}}
    cohort=choose_runtime(groups,32 if split=='development'else 128,26110806)
    plans={r['id']:r for r in records}
    for gate in (['raw']if split=='development'else['raw','self']):
        data=episodes(model,tokenizer,cohort,arm,plans,vm,gate)
        result[gate]={'summary':episode_metrics(data),'records':data,
                     'panels':{p:episode_metrics([r for r in data if r['panel']==p])for p in ['known','novel']}}
    return result


def key(report):
    panels=report['primary']['panels'];raw=report['raw']['summary']
    return [min(r['passed']/r['total']for r in panels.values()),report['primary']['summary']['passed'],
            raw['passed']-raw['false_DONE'], -raw['false_DONE']]


def brief(report):return {k:v['summary']for k,v in report.items()if isinstance(v,dict)and'summary'in v}
