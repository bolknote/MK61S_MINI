"""Same training/development, a newly sealed final set, original decoder context."""
import json
import random
import shutil
from ab_common import ROOT,BASE,HERE,INITIAL,INITIAL_PACKET,read,write,sha,output_ids
from aa_data import repartition,seeds
from aa_common import BASE as HISTORICAL
from ha_data import basic_tasks,composite_tasks,algorithm_tasks
from hr_data import boundary_tasks,hard_tasks
from hd_x_data import generate as x_tasks
from full_isa_vm import FullVM
from transformers import AutoTokenizer
from tasks import save_jsonl


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    assert(BASE/'data-frozen.json').exists()
    vm=FullVM();tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    copied=['catalog.json','isa-audit.jsonl','legacy-development.jsonl','validation.jsonl','validation-seeds.jsonl',
            'training-tasks.jsonl','train-seeds.jsonl','train.jsonl','expert-lessons.jsonl','replay-light.jsonl']
    for n in copied:shutil.copyfile(BASE/n,ROOT/n)
    shutil.copytree(BASE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    seen=set()
    for source in [BASE,HISTORICAL]:
        for n in ['train.jsonl','training-tasks.jsonl','validation.jsonl','fresh.jsonl','sft-light.jsonl']:
            if(source/n).exists():seen.update((t['angle'],t['task'])for t in read(source/n))
    seed=715113
    candidates=basic_tasks(vm,'fresh',160,seed)+boundary_tasks(vm,'fresh',80,seed+1)
    candidates+=composite_tasks(vm,'fresh',160,seed+2)+hard_tasks(vm,'fresh',120,seed+3)
    candidates+=x_tasks(vm,'fresh',35,seed+4)+algorithm_tasks(vm,'fresh',60,seed+5)
    random.Random(seed+6).shuffle(candidates);fresh=[]
    for task in candidates:
        if(task['angle'],task['task'])in seen:continue
        t=repartition(task,len(fresh),'fresh');t['id']='ab-'+t['id']
        if(t['angle'],t['task'])in seen:continue
        seen.add((t['angle'],t['task']));fresh.append(t)
        if len(fresh)==250:break
    assert len(fresh)==250,len(fresh)
    save_jsonl(ROOT/'fresh.jsonl',fresh);save_jsonl(ROOT/'fresh-seeds.jsonl',seeds(fresh,vm))
    write(ROOT/'output-token-ids.json',output_ids(tokenizer))
    policy={'context':1024,'batch':128,'format_warmup_steps':400,'stages':3,'steps_per_stage':400,
            'warmup_lr':5e-4,'lr':2e-6,'action_embedding_lr_factor':10.,'warmup_head_only':True,'weight_decay':.01,
            'body_loss_weight':.5,'action_loss_weight':1.,'dpo_beta':.2,'dpo_weight':.5,'dpo_rows':24,
            'seed':712411,'max_turns':10,'mining_episodes_per_arm_per_stage':160,
            'shared_on_policy_union':True,'same_sft_draws_both_arms':True,
            'release':{'validation_episodes':500,'false_DONE':0,'strict_solved_rate_min':.8,
                       'documented_opcodes_required':648,'legacy_min':66},
            'selection_order':['release_eligible','retention','solved_minus_twice_false_DONE','minus_false_DONE','legacy'],
            'fresh_used_for_selection':False,'action_preferences_only':True,
            'neural_body_headers':'original tag token sequence, deterministic, no answer lookup',
            'wire_end_token':30,'action_wire_tokens_not_fed_to_KV':True,'segmented_primer':True,
            'diagnosis_is_hypothesis_and_incorrect_citation_does_not_block_patch':True,
            'changed_after_v1_development_not_v1_final_exam':True}
    write(ROOT/'policy.json',policy)
    files=copied+['fresh.jsonl','fresh-seeds.jsonl','output-token-ids.json','policy.json']
    write(ROOT/'data-frozen.json',{'files':{n:sha(ROOT/n)for n in files},
         'initial_master_sha256':sha(INITIAL/'model.safetensors'),'initial_packet_sha256':sha(INITIAL_PACKET),
         'new_counts':{'train':1000,'validation':250,'fresh':250},'training_task_count':3191,
         'expert_lessons':len(read(ROOT/'expert-lessons.jsonl')),'original_exam_results_unchanged':True,
         'v1_training_and_development_reused':True,'fresh_disjoint_from_v1_and_historical_exact_texts':True,
         'frozen_before_updates':True,'public_cases_1_to_4':True,'semantic_alternative_programs_accepted':True})
    print(json.dumps({'ready':True,'new_fresh':len(fresh),'head_only_warmup':True,'train_reused_from_v1':True}),flush=True)


if __name__=='__main__':main()
