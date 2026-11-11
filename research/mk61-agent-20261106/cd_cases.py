"""Freeze training-only branch seeds and proven non-review successes before rollouts."""
import collections
import copy
import hashlib
import random
from safetensors.torch import load_file
from transformers import AutoTokenizer
from cd_common import ROOT,CC_ROOT,CC_RESULTS,ACTOR,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS
from cd_state import make_session,event
from bj_runtime import Session
from aq_protocol import prompt_ids
from ar_spec import infer
from be_language import paths3
from bl_spec import install
from bl_vm import CachedVM

def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'cases-frozen.json').exists():return
    install();vm=CachedVM(1024);tok=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True)
    proof=read(ROOT/'parent-features-proof.json');assert sha(ROOT/'parent-features.safetensors')==proof['sha256']
    assert sha(CC_ROOT/'lessons.jsonl')==proof['source_lessons_sha256']and sha(ACTOR/'model.mkqb')==proof['frozen_parent_packet_sha256']
    old=rows(CC_ROOT/'lessons.jsonl');cache=load_file(str(ROOT/'parent-features.safetensors'));assert len(cache['hidden'])==len(old)
    held={tuple(t)for v in read(ROOT/'ast-frozen.json')['held_triples'].values()for t in v};retained={g['id']for g in rows(ROOT/'retention.jsonl')}
    index={digest(r['prompt']):i for i,r in enumerate(old)};assert len(index)==len(old);write(ROOT/'parent-feature-index.json',index)
    replay=[]
    for i,r in enumerate(old):
        if r['task_id']in retained or r['action']=='diag':continue
        label=ACTIONS.index(r['action'])
        if int(cache['teacher_logits'][i].argmax())!=label:continue
        if not(r.get('retain')or r.get('successful_repair_replay')or(r['action']=='unsure'and r['origin']=='budget_control')):continue
        assert not paths3(r['target_spec']['X'])&held and not paths3(r['state']['declared_spec']['X'])&held
        replay.append({'id':'cd:replay:'+str(i),'task_id':r['task_id'],'prompt':r['prompt'],'input_tokens':r['input_tokens'],
            'cache_index':i,'action':r['action'],'review':False,'retain':True,'origin':'verified_success_replay',
            'repair_replay':bool(r.get('successful_repair_replay')),'correct_done':r['code_correct']and r['spec_correct']and r['action']=='done'})
    assert replay and any(r['repair_replay']for r in replay)and any(r['correct_done']for r in replay)
    save_rows(ROOT/'replay.jsonl',replay)
    goals=rows(ROOT/'retired-train.jsonl')+rows(ROOT/'train.jsonl');byid={g['id']:g for g in goals};unique={digest(g['id']+'\n'+g['task']):g for g in goals};rng=random.Random(261129114)
    seeds=[];used=set();goalmap={};stats=collections.Counter()
    def add(seed,g):
        key=digest(seed['prompt'])
        if key in used:return False
        if len(prompt_ids(tok,seed['prompt']))>=1016:stats['overlength_seed_excluded']+=1;return False
        if paths3(seed['initial_spec']['X'])&held:return False
        s=make_session(seed,g,vm)
        try:
            if paths3(infer(s.body,s.pool,g['spec']['angle'])['X'])&held:return False
        except(ValueError,ArithmeticError,KeyError):pass
        assert not paths3(g['spec']['X'])&held
        gid=digest(g['id']+'\n'+g['task']);goalmap[gid]=g;seed.update(id=f'cd:case:{len(seeds):04}',goal_key=gid,prompt_sha256=key,
            input_tokens=len(prompt_ids(tok,seed['prompt'])),cache_index=index.get(key))
        seeds.append(seed);used.add(key);return True
    # Retired actual failures and late states, reconstructed before a normal call.
    real=[]
    for role in ['parent','final']:
        report=read(CC_RESULTS/f'closed-{role}.json')
        for record in report['own']['records']:
            g=byid.get(record['task_id'])
            if g is None:continue
            if record['pass']and not record['false_DONE_claims']:continue
            for at,h in enumerate(record['history']):
                gen=h.get('generation',{})
                if gen.get('profile')!='actor'or gen.get('codec_error'):continue
                prefix=record['history'][:at]
                if any(x['kind']in ['generation_error','replan']for x in prefix)or len(prefix)>6:continue
                seed={'initial_body':g['reference_body']if record['initially_correct']else g['bad_body'],
                    'initial_spec':record['initial_spec'],'prefix':[event(x)for x in prefix],'start_case':None,
                    'prompt':h['prompt'],'origin':'retired_actual_state','source_role':role}
                real.append((seed,g))
    rng.shuffle(real)
    for seed,g in real:
        if len(seeds)>=64:break
        try:add(seed,g)
        except(AssertionError,ValueError):stats['unreconstructible_real_seed_excluded']+=1
    real_count=len(seeds)
    # Fixed reserve order; all four SPEC/code cases stay adjacent for a goal.
    fresh={g['id']:g for g in rows(ROOT/'train.jsonl')};first=list(fresh.values());rng.shuffle(first);selected=first[:32]
    rest=list(unique.values());rng.shuffle(rest);selected_keys={digest(g['id']+'\n'+g['task'])for g in selected}
    for g in rest:
        k=digest(g['id']+'\n'+g['task'])
        if k not in selected_keys:selected.append(g);selected_keys.add(k)
        if len(selected)==192:break
    for g in selected:
        case=int(digest(g['id'])[-1],16)%2
        for spec_ok in [False,True]:
            for code_ok in [False,True]:
                body=g['reference_body']if code_ok else g['bad_body'];spec=g['spec']if spec_ok else g['bad_spec']
                s=Session(g,body,vm,'spec',spec,True,start_case=case)
                add({'initial_body':body,'initial_spec':spec,'prefix':[],'start_case':case,'prompt':s.request(),
                    'origin':'four_way_initial','spec_correct_seed':spec_ok,'code_correct_seed':code_ok},g)
    assert len(seeds)>=400 and len(goalmap)>=96
    save_rows(ROOT/'utility-seeds.jsonl',seeds);save_rows(ROOT/'utility-goals.jsonl',[{'key':k,'goal':g}for k,g in goalmap.items()])
    write(ROOT/'case-design.json',{'real_states':real_count,'maximum_cases':len(seeds),'distinct_training_goals':len(goalmap),'replay_states':len(replay),
        'minimum_cases_before_stopping':448,'minimum_useful_review_labels':32,'minimum_nonreview_labels':64,
        'fixed_reserve_order':True,'only_training_goals_used':True,'retention_excluded':True,'all_public_prompts_reconstructed':True,'stats':dict(stats)})
    names=['replay.jsonl','utility-seeds.jsonl','utility-goals.jsonl','case-design.json','parent-feature-index.json','parent-features.safetensors','parent-features-proof.json']
    write(ROOT/'cases-frozen.json',{'complete':True,'files':{n:sha(ROOT/n)for n in names},'design':read(ROOT/'case-design.json')})
    print(read(ROOT/'case-design.json'),flush=True)

if __name__=='__main__':main()
