"""Known nineteen mistakes: fixed bad hypotheses and separate translation probes."""
from bc_common import PARENT,read,rows
from az_runtime import Session
from ba_lessons import wrong_program
from ay_eval import primary,episode_metrics
from aq_eval import generate
from full_isa_vm import FullVM
from ar_spec import verify

def evaluate(model,tokenizer):
    old=read(PARENT/'spec/closed.json');failures=[r for r in old['self']['records']if r['finished']and not r['program_correct']]
    goals={g['id']:g for g in rows(PARENT/'closed-clean.jsonl')};vm=FullVM();jobs=[]
    used=[goals[k]for k in sorted({r['task_id']for r in failures})]
    translation=primary(model,tokenizer,used,'spec',vm)
    for r in failures:
        g=goals[r['task_id']];body=g['reference_body']if r['initially_correct']else wrong_program(g,vm,r['initial'])[0]
        jobs.append((g,r,Session(g,body,vm,'spec',r['declared_spec'],True)))
    for turn in range(12):
        active=[(g,r,s)for g,r,s in jobs if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
        if not active:break
        prompts=[s.request()for g,r,s in active];values=generate(model,tokenizer,prompts)
        for(g,r,s),p,v in zip(active,prompts,values):
            if v.get('codec_error'):
                s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
            try:s.apply_action(v['action'],v['body'])
            except (ValueError,ArithmeticError,RuntimeError)as e:
                s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
            s.history[-1].update(prompt=p,generation=v)
    records=[]
    for g,r,s in jobs:
        correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
        records.append({'id':r['id'],'task_id':g['id'],'finished':s.finished,'program_correct':correct,'abstained':s.abstained,
            'false_DONE':bool(s.finished and not correct),'safe_exit':bool(s.abstained and correct),'history':s.history})
    return {'known_training_regression_not_fresh_exam':True,'fixed_old_hypotheses_not_updated':True,
       'translation':{'total':len(translation),'passed':sum(r['program_correct']for r in translation),'records':translation},
       'summary':{'total':len(records),'false_DONE':sum(r['false_DONE']for r in records),'safe_correct_code_UNSURE':sum(r['safe_exit']for r in records),
          'correct_final_code':sum(r['program_correct']for r in records),'accepted_DONE':sum(r['finished']for r in records),'abstained':sum(r['abstained']for r in records)},'records':records}
