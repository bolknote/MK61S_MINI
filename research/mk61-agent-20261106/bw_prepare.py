"""Freeze the routing policy, fixed weights, selection rules and unseen exam."""
import time
import shutil
import torch
from bw_common import ROOT,HERE,SOURCE,BV_ROOT,BV_RESULTS,MODELS,ROUTES,read,write,rows,save_rows,sha,previous_check,output_ids,compact_head
from bw_eval import Cache
from be_model import load
from bu_eval import CONFIG


def main():
    previous_check();assert not(ROOT/'frozen.json').exists()
    shutil.copytree(SOURCE,MODELS['actor'],dirs_exist_ok=True)
    ast=read(ROOT/'ast-frozen.json');teacher=read(ROOT/'teacher-frozen.json')
    for files in [ast['files'],teacher['files']]:
        for n,d in files.items():assert sha(ROOT/n)==d,n
    policy={'optimizer_updates':0,'routes':{k:list(v)for k,v in ROUTES.items()},'route_order':list(ROUTES),
        'U':'BU1500 translator','N':'BV recovery +2400 translator','actor':'original immutable actor',
        'selection':'maximum completed, repairs, correct finishes after all no-regression gates against UU; ties prefer UU, then NU',
        'selection_gates':['first_SPEC','compositions','completed','repairs','correct_finishes','accepted_false_DONE','corruption','false_claim_episodes','wrong_SPEC_false_DONE'],
        'closed_used_for_selection':False,'context':1024,'KV':'FP32','max_actions':12,'Q4':True,
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
        'Qwen_service_changes':False,'main_profile_replacement':False,'physical_device_access':False,
        'decoder_cache':'exact immutable profile, complete prompt, forced-action key; same action and context budgets',
        'diagnostic_goals_are_retired_BV_closed_cases':True,'development_goals':64,'closed_goals':256,'closed_families':32}
    write(ROOT/'policy.json',policy)
    write(ROOT/'expected-development-UU.json',read(BV_RESULTS/'parent-development.json'))
    ids={'bv:closed:unary:000055','bv:closed:unary:000075'}
    save_rows(ROOT/'diagnostic.jsonl',[g for g in rows(BV_ROOT/'closed.jsonl')if g['id']in ids])
    assert len(rows(ROOT/'diagnostic.jsonl'))==2
    parent=read(BV_ROOT/'parent-fit.json');child=read(BV_RESULTS/'fit-2400.json')
    write(ROOT/'known-fit.json',{'source':'retired BV training controls; fixed profiles, not a new test',
        'U':{k:parent[k]['summary']for k in ['hard','retention','composition']},
        'N':{k:child[k]['summary']for k in ['hard','retention','composition']}})
    cache=Cache();proof=[];tok=None
    for profile,folder in MODELS.items():
        model,t=load(folder,'cpu')
        if tok is None:tok=t
        else:assert tok.get_vocab()==t.get_vocab()
        compact_head(model,output_ids(tok))
        report=read(BV_RESULTS/('closed-final.json'if profile=='N'else'closed-parent.json'))
        if profile=='actor':
            h=next(h for r in report['own']['records']for h in r['history']if h.get('generation',{}).get('profile')=='unchanged_actor'and not h['generation'].get('codec_error'))
            probes=[(h['prompt'],h['generation'],None)]
        else:
            r=next(x for x in report['primary']['records']if x['id']=='bv:closed:unary:000055')
            h=next(h for r in report['own']['records']if r['id']=='bv:closed:unary:000055:correct'for h in r['history']if h['kind']=='replan')
            probes=[(r['prompt'],r['generation'],'write'),(h['prompt'],h['generation'],'write')]
        for prompt,saved,forced in probes:
            a=cache.generate(profile,model,tok,prompt,forced);b=cache.generate(profile,model,tok,prompt,forced)
            assert a['generated_token_ids']==b['generated_token_ids']==saved['generated_token_ids']and b['cache_hit']
            proof.append({'profile':profile,'forced':forced,'saved_B200_CPU_and_cache_equal':True})
        # Cache is bound to the exact model object; don't reuse it after freeing.
        cache=Cache();del model
    write(ROOT/'router-preflight.json',{'complete':True,'optimizer_updates':0,'proof':proof,'weights_modified':False})
    sources={**read(BV_ROOT/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bw_*.py')if p.name not in ['bw_native.py','bw_finish.py']}}
    files={**ast['files'],**teacher['files'],**{n:sha(ROOT/n)for n in ['ast-frozen.json','teacher-frozen.json','policy.json','expected-development-UU.json','diagnostic.jsonl','known-fit.json','router-preflight.json']}}
    if(ROOT/'pre-inference-repair.json').exists():
        repair=read(ROOT/'pre-inference-repair.json')
        assert sha(ROOT/'policy.json')==repair['unchanged_policy_sha256']
        for n,d in repair['unchanged_data_files'].items():assert sha(ROOT/n)==d,n
        files['pre-inference-repair.json']=sha(ROOT/'pre-inference-repair.json')
    fingerprints={profile:{str(p.relative_to(folder)):sha(p)for p in [folder/'model.mkqb',folder/'manifest.json',*sorted((folder/'hf').iterdir())]if p.is_file()}for profile,folder in MODELS.items()}
    write(ROOT/'frozen.json',{'sources':sources,'files':files,'models':fingerprints,'closed_student_generations_seen':False,'optimizer_updates':0,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'preflight_streams':len(proof),'all_profiles_frozen':True})
    s=read(HERE/'work-state.json');s.update(phase='spec_phase_routing_prepared',active_experiment='spec-phase-routing-v1',all_own_jobs_complete=False,
        latest_phase_routing={'phase':'prepared','optimizer_updates':0,'directory':str(ROOT),'model_weights_changed':False});write(HERE/'work-state.json',s)
    print(read(ROOT/'prepared.json'),flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
