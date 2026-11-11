"""Freeze the already retired BX panels and their exact previously run controls."""
import shutil
import time
from by_common import ROOT,BX_ROOT,BX_RESULTS,ACTOR,HERE,read,write,rows,sha,previous_check
from by_eval import oracle_generation
from bj_runtime import Session,render
from ay_runtime import goal_state
from ay_codec import encode,decode,compile_spec
from bl_spec import install
from bl_vm import CachedVM
from ar_spec import verify
from transformers import AutoTokenizer
from bu_model import frozen_digest


def main():
    previous_check();ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    policy={'optimizer_updates':0,'context':1024,'KV':'FP32','max_actions':12,'weights':'Q4',
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
        'Qwen_service_changes':False,'main_profile_replacement':False,'physical_device_access':False,
        'panels':{'development':128,'closed':256},'panels_are_retired_diagnostics':True,
        'oracle_phases':['initial','scheduled_replan'],'actor_unchanged':True,
        'ordinary_WRITE_uses_actor':True,'RUN_gate_rollback_and_action_budget_unchanged':True,
        'selection_or_training':False,'not_an_independent_agent_score':True}
    write(ROOT/'policy.json',policy)
    baseline_files={}
    for split,files in [('development',{'parent':'parent-development.json','final':'development-1200.json'}),
                        ('closed',{'parent':'closed-parent.json','final':'closed-final.json'})]:
        shutil.copyfile(BX_ROOT/(split+'.jsonl'),ROOT/(split+'.jsonl'))
        assert sha(BX_RESULTS/(split+'.jsonl'))==sha(ROOT/(split+'.jsonl'))
        for role,name in files.items():
            target=f'baseline-{split}-{role}.json';shutil.copyfile(BX_RESULTS/name,ROOT/target)
            baseline_files[target]={'source_name':name,'sha256':sha(ROOT/target)}
    install();vm=CachedVM();tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True)
    checks=0;oracle_calls=0;max_input=0
    for split,n in policy['panels'].items():
        goals=rows(ROOT/(split+'.jsonl'));assert len(goals)==n
        for role in ['parent','final']:
            records=read(ROOT/f'baseline-{split}-{role}.json')['own']['records']
            expected={g['id']+':'+label for g in goals for label in ['correct',g['error_kind']]}
            assert {r['id']for r in records}==expected
        for g in goals:
            body=encode(g['spec'],g['pool']);assert decode(body,g['pool'],g['spec']['angle'])==g['spec']
            program=compile_spec(g['spec'],g['pool']);assert program==g['reference_body']
            assert verify(vm,program,g['pool'],g['spec'],g['audit_inputs'])['status']=='TESTED'
            assert verify(vm,g['bad_body'],g['pool'],g['spec'],g['audit_inputs'])['status']!='TESTED'
            s=Session(g,g['bad_body'],vm,'spec',g['spec'],True)
            for phase,prompt in [('initial',render(goal_state(g),'spec')),('runtime',s.replan_request())]:
                output=oracle_generation(tok,prompt,g,phase);assert not output['codec_error']
                max_input=max(max_input,output['input_tokens']);oracle_calls+=1
            before=list(s.body);s.apply_replan(body)
            assert s.body==before and s.declared_spec==g['spec'] and s.replan_count==1
            checks+=1
    proof={'complete':True,'optimizer_updates':0,'goals':checks,'oracle_codec_context_checks':oracle_calls,
        'max_oracle_input_tokens':max_input,'gold_compiles_to_unchanged_reference':True,'bad_starts_still_wrong':True,
        'replan_keeps_program_and_counts_action':True,'actor_sha256':sha(ACTOR/'model.mkqb')}
    write(ROOT/'CPU-preflight.json',proof)
    file_names=['policy.json','development.jsonl','closed.jsonl','CPU-preflight.json',*baseline_files]
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('by_*.py')if p.name not in ['by_native.py','by_finish.py']},
        'files':{n:sha(ROOT/n)for n in file_names},'actor':{str(p.relative_to(ACTOR)):sha(p)for p in ACTOR.rglob('*')if p.is_file()},
        'baseline_provenance':baseline_files,'oracle_generations_seen':False,'optimizer_updates':0,'unix':time.time()})
    write(ROOT/'prepared.json',proof)
    path=HERE/'work-state.json';state=read(path)
    state.update(active_experiment='spec-gold-cycle-diagnostic-v1',all_own_jobs_complete=False,phase='gold_SPEC_cycle_diagnostic_prepared',
        latest_gold_cycle_diagnostic={'phase':'prepared','optimizer_updates':0,'directory':str(ROOT),'independent_solution_score':False})
    write(path,state);print(proof,flush=True)


if __name__=='__main__':main()
