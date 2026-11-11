"""Freeze the already opened BC cohort and exact starting states; no gradients."""
import copy
import json
import shutil
import time
from bd_common import ROOT,PARENT,SOURCE,MODEL,HERE,read,write,rows,save_rows,sha,check_frozen
from bc_common import check_frozen as old_check
from bc_self import wrong_program
from az_runtime import Session
from full_isa_vm import FullVM
from ar_spec import equivalent


def main():
    assert not(ROOT/'frozen.json').exists();old_check();ROOT.mkdir(exist_ok=True)
    groups=rows(PARENT/'closed-clean.jsonl');by_id={g['id']:g for g in groups}
    report=read(PARENT/'spec/closed.json');baseline={'primary':report['primary'],'self':report['self']}
    write(ROOT/'baseline.json',baseline);save_rows(ROOT/'groups.jsonl',groups)
    vm=FullVM();jobs=[];previous=baseline['self']['records'];assert len(previous)==256
    for at in range(0,len(previous),2):
        a,b=previous[at:at+2];assert a['task_id']==b['task_id']and a['initially_correct']and not b['initially_correct']
        goal=by_id[a['task_id']];kind=['operation','argument','order'][(at//2)%3]
        bad=wrong_program(goal,vm,kind)[0]
        for old,body in [(a,goal['reference_body']),(b,bad)]:
            own=Session(goal,body,vm,'spec',old['declared_spec'],True)
            oracle=Session(goal,body,vm,'spec',goal['spec'],True)
            assert own.request()==old['history'][0]['prompt']==oracle.request(),old['id']
            jobs.append({'id':old['id'],'task_id':goal['id'],'initial':old['initial'],
                'initially_correct':old['initially_correct'],'body':copy.deepcopy(body),
                'own_spec':old['declared_spec'],'initial_prompt_sha256':__import__('hashlib').sha256(own.request().encode()).hexdigest(),
                'own_spec_correct':equivalent(old['declared_spec'],goal['spec'],goal['audit_inputs'])['tested_equal']})
        if at%64==0:print(json.dumps({'frozen_start_states':at+2,'total':256}),flush=True)
    save_rows(ROOT/'jobs.jsonl',jobs)
    MODEL.mkdir(parents=True,exist_ok=True)
    for name in ['model.mkqb','model.mka','manifest.json']:
        shutil.copyfile(SOURCE/name,MODEL/name)
    shutil.copytree(SOURCE/'hf',MODEL/'hf',dirs_exist_ok=True)
    write(ROOT/'policy.json',{'kind':'opened-cohort 2x2 diagnostic, not a new closed exam',
        'tasks':128,'episodes_per_arm':256,'primary_translation_tasks':398,'max_actions':12,'batch':24,
        'arms':{'own_actor':'original own SPEC + unchanged Q4 learned actions; exact replay',
            'oracle_actor':'gold SPEC in private checker only + unchanged Q4 learned actions',
            'own_mechanical':'original own SPEC + deterministic compile/verify/RUN/DONE controller',
            'oracle_mechanical':'gold SPEC + same deterministic controller; offline ceiling'},
        'same_goals_pools_starting_programs_cases_and_input_banks':True,
        'actor_initial_prompts_identical_for_own_and_oracle':True,
        'oracle_feedback_may_reveal_gold_spec_after_real_rejection':True,
        'deterministic_controller':'retain existing code if it tests against supplied SPEC on checker inputs; otherwise compile that SPEC; perform missing public RUNs; request mechanically gated DONE; on unavailable spec, compile/runtime/checker failure use UNSURE without retry',
        'deterministic_controller_never_reads_task_gold_except_in_explicit_oracle_arm':True,
        'actor_prefix_cache':'reuse only exact prompt matches from the same frozen Q4 model, action/body/token stream checked; additional prompts generated with same decoder',
        'same_session_protocol_as_BC':True,'quantization':'Q4, actual packed weights; FP32 compute and KV',
        'optimizer_updates':0,'teacher_calls':0,'new_weights_selected':False,
        'scope':'straight-line arithmetic and optional result store, bounded numerical checks; no branches or loops',
        'freeze_before_new_model_generations':True,'unix':time.time()})
    files=[ROOT/n for n in ['baseline.json','groups.jsonl','jobs.jsonl','policy.json']]+[p for p in MODEL.rglob('*')if p.is_file()]
    old_sources=read(PARENT/'frozen.json')['sources']
    sources={**old_sources,**{p.name:sha(p)for p in HERE.glob('bd_*.py')if not p.name.endswith(('_remote.py','_report.py','_native.py','_finish.py'))}}
    write(ROOT/'frozen.json',{'sources':sources,'files':{str(p.relative_to(ROOT)):sha(p)for p in files},
        'source_experiment':'semantic-spec-selfcheck-v1','source_Q4_sha256':sha(SOURCE/'model.mkqb'),
        'optimizer_updates':0,'unix':time.time()})
    check_frozen();write(ROOT/'prepared.json',{'complete':True,'jobs':len(jobs),'goals':128,
        'initial_prompt_pairs_identical':256,'Q4_model_copied_exactly':True,'optimizer_updates':0})
    print(json.dumps({'prepared':True,'episodes':256,'arms':4,'optimizer_updates':0}),flush=True)


if __name__=='__main__':main()
