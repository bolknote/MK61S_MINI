"""Freeze one compact format and check public-field preservation on real logs."""
import collections
import json
import re
import shutil
import statistics
import time
from transformers import AutoTokenizer
from bz_common import ROOT,BY_ROOT,BY_RESULTS,ACTOR,HERE,read,write,rows,sha,previous_check
from bz_runtime import shorten
from aq_protocol import prompt_ids


def facts(text):
    # Independently extract all variable/public payload fields, excluding static prose.
    prefix=('Константы:','Задача:','Открытые входы:','Версия кода ','Факт ',
            'Текущий HEX','Эмулятор:','Диагноз сети,','Текущая гипотеза:','DIAG 04 ')
    data=[line for line in text.splitlines()if line.startswith(prefix)or re.match(r'^[0-9A-F]{4}: ',line)]
    budget=re.search(r'^Осталось действий: (\d+)\.',text,re.M);assert budget
    return data,int(budget[1]),text.splitlines()[0],text.splitlines()[-1]


def stats(values):
    return {'count':len(values),'min':min(values),'mean':statistics.mean(values),'median':statistics.median(values),'max':max(values)}


def main():
    previous_check();assert read(BY_ROOT/'pipeline-complete.json')['complete']
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    policy={'optimizer_updates':0,'context':1024,'KV':'FP32','max_actions':12,'weights':'Q4',
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
        'Qwen_service_changes':False,'main_profile_replacement':False,'physical_device_access':False,
        'panels':{'development':128,'closed':256},'panels_are_retired_diagnostics':True,
        'modes':['gold','own'],'actor_unchanged':True,'translator':'BU1500 unchanged',
        'compact_candidates':1,'only_ordinary_actor_prompt_changes':True,'initial_replan_prompts_unchanged':True,
        'selection':'both modes on development: at least2 more true completions, no lower repairs or correct-start completions, no more accepted false DONE or final corruption',
        'closed_used_for_selection':False,'RUN_gate_rollback_action_budget_unchanged':True,
        'gold_is_external_answer_not_independent_score':True}
    write(ROOT/'policy.json',policy);baseline_files={}
    for split in ['development','closed']:
        shutil.copyfile(BY_ROOT/(split+'.jsonl'),ROOT/(split+'.jsonl'))
        for mode in ['gold','own']:
            source=BY_RESULTS/(split+'-gold.json')if mode=='gold'else BY_ROOT/f'baseline-{split}-parent.json'
            name=f'baseline-{split}-{mode}.json';shutil.copyfile(source,ROOT/name)
            baseline_files[name]={'source':str(source.relative_to(BY_ROOT)),'sha256':sha(ROOT/name)}
    tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True)
    before=[];after=[];first=[];unique={};by_panel={};checked=0
    for split in ['development','closed']:
        for mode in ['gold','own']:
            value=read(ROOT/f'baseline-{split}-{mode}.json');report_before=[];report_after=[];first_before=first_after=0
            goals=rows(ROOT/(split+'.jsonl'));expected={g['id']+':'+kind for g in goals for kind in ['correct',g['error_kind']]}
            assert {r['id']for r in value['own']['records']}==expected
            for r in value['own']['records']:
                actors=[h for h in r['history']if h.get('generation',{}).get('profile')=='actor']
                for i,h in enumerate(actors):
                    p=h['prompt']
                    if p not in unique:
                        short=shorten(p);assert facts(short)==facts(p)
                        a=len(prompt_ids(tok,p));b=len(prompt_ids(tok,short));assert b<a
                        unique[p]=(a,b);before.append(a);after.append(b)
                    a,b=unique[p];report_before.append(a);report_after.append(b);checked+=1
                    if i==0:first_before+=a>=1016;first_after+=b>=1016
            by_panel[split+'_'+mode]={'before':stats(report_before),'after':stats(report_after),
                'first_call_overflow_before':first_before,'first_call_overflow_after_on_same_states':first_after,
                'same_states_only_not_a_model_quality_measure':True}
    proof={'complete':True,'optimizer_updates':0,'real_actor_prompts_checked':checked,'unique_prompts':len(unique),
        'all_public_payload_fields_verbatim':True,'angle_and_remaining_actions_preserved':True,
        'before':stats(before),'after':stats(after),'mean_tokens_saved':statistics.mean(a-b for a,b in zip(before,after)),
        'by_panel':by_panel,'new_trajectories_not_measured_yet':True}
    write(ROOT/'CPU-preflight.json',proof)
    names=['policy.json','development.jsonl','closed.jsonl','CPU-preflight.json',*baseline_files]
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('bz_*.py')if p.name not in ['bz_native.py','bz_finish.py','bz_pipeline.py']},
        'files':{n:sha(ROOT/n)for n in names},'baseline_provenance':baseline_files,'new_model_generations_seen':False,'optimizer_updates':0,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'public_fields_verified':True,'unique_prompts':len(unique)})
    path=HERE/'work-state.json';state=read(path);state.update(active_experiment='spec-compact-prompt-v1',all_own_jobs_complete=False,
        phase='compact_prompt_prepared',latest_compact_prompt_diagnostic={'phase':'prepared','optimizer_updates':0,'directory':str(ROOT)})
    write(path,state)
    print(json.dumps({k:v for k,v in proof.items()if k!='by_panel'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
