"""Freeze the one-at-a-time variants and prove unchanged public payloads."""
import collections
import json
import shutil
import time
from transformers import AutoTokenizer
from ca_common import ROOT,BZ_ROOT,BZ_RESULTS,ACTOR,HERE,VARIANTS,read,write,sha,previous_check
from ca_runtime import shorten
from bz_runtime import shorten as combined
from bz_prepare import facts
from aq_protocol import prompt_ids


def main():
    previous_check();assert read(BZ_ROOT/'pipeline-complete.json')['complete']
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    policy={'optimizer_updates':0,'context':1024,'KV':'FP32','max_actions':12,'weights':'Q4',
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
        'Qwen_service_changes':False,'main_profile_replacement':False,'physical_device_access':False,
        'panels':{'development':128,'closed':256},'panels_are_retired_diagnostics':True,'modes':['gold','own'],
        'variants':list(VARIANTS),'candidate_count':3,'variant_order':list(VARIANTS),'actor_unchanged':True,'translator':'BU1500 unchanged',
        'initial_replan_prompts_unchanged':True,'only_one_static_section_changes_per_variant':True,
        'selection':'both modes development: at least2 more true completions, no lower repairs/correct-start completions, no more accepted false DONE or final corruption',
        'eligible_rank':'own completed, own repairs, gold completed, gold repairs, fewer own accepted false DONE, fewer own corruptions, tokens saved',
        'audit':'one eligible winner; if none eligible, original remains selected and the highest-ranked new variant is audited as diagnostic only',
        'closed_used_for_selection':False,'RUN_gate_rollback_action_budget_unchanged':True,'gold_is_external_answer':True}
    write(ROOT/'policy.json',policy);provenance={}
    for split in ['development','closed']:
        shutil.copyfile(BZ_ROOT/(split+'.jsonl'),ROOT/(split+'.jsonl'))
        for mode in ['gold','own']:
            name=f'baseline-{split}-{mode}.json';source=BZ_ROOT/name;shutil.copyfile(source,ROOT/name)
            provenance[name]={'source':str(source.relative_to(BZ_ROOT)),'sha256':sha(ROOT/name)}
            if split=='development':
                name=f'joint-development-{mode}.json';source=BZ_RESULTS/f'development-{mode}.json';shutil.copyfile(source,ROOT/name)
                provenance[name]={'source':str(source.relative_to(BZ_ROOT)),'sha256':sha(ROOT/name)}
    tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True);prompts=set();checks=0;distributions={v:collections.Counter()for v in VARIANTS};first={}
    for split in ['development','closed']:
        for mode in ['gold','own']:
            value=read(ROOT/f'baseline-{split}-{mode}.json')
            for r in value['own']['records']:
                actors=[h for h in r['history']if h.get('generation',{}).get('profile')=='actor']
                for i,h in enumerate(actors):
                    p=h['prompt'];old=len(prompt_ids(tok,p))
                    if p not in prompts:
                        assert shorten(p,'original')==p and shorten(p,'all')==combined(p)
                        for variant in VARIANTS:
                            short=shorten(p,variant);assert facts(short)==facts(p)
                            saved=old-len(prompt_ids(tok,short));assert saved>0
                            distributions[variant][saved]+=1
                        prompts.add(p)
                    if i==0:
                        key=split+'_'+mode
                        row=first.setdefault(key,{'original':0,**{v:0 for v in VARIANTS}});row['original']+=old>=1016
                        for variant in VARIANTS:row[variant]+=len(prompt_ids(tok,shorten(p,variant)))>=1016
                    checks+=1
    assert all(len(c)==1 for c in distributions.values()),distributions
    saved={v:next(iter(c))for v,c in distributions.items()};assert sum(saved.values())==126
    proof={'complete':True,'optimizer_updates':0,'real_actor_prompts_checked':checks,'unique_prompts':len(prompts),
        'public_payload_fields_verbatim':True,'angle_and_remaining_preserved':True,'other_two_static_sections_verbatim':True,
        'single_sections_recompose_previous_combined_variant_exactly':True,'tokens_saved':saved,
        'saved_distribution':{v:dict(c)for v,c in distributions.items()},'first_call_overflow_on_old_states':first,
        'new_model_trajectories_not_yet_measured':True}
    write(ROOT/'CPU-preflight.json',proof)
    names=['policy.json','development.jsonl','closed.jsonl','CPU-preflight.json',*provenance]
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('ca_*.py')if p.name not in ['ca_native.py','ca_finish.py','ca_pipeline.py']},
        'files':{n:sha(ROOT/n)for n in names},'baseline_provenance':provenance,'new_model_generations_seen':False,'optimizer_updates':0,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'public_fields_verified':True,'unique_prompts':len(prompts),'tokens_saved':saved})
    path=HERE/'work-state.json';state=read(path);state.update(active_experiment='spec-prompt-parts-v1',all_own_jobs_complete=False,
        phase='prompt_parts_prepared',latest_prompt_parts_diagnostic={'phase':'prepared','optimizer_updates':0,'directory':str(ROOT)})
    write(path,state);print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
