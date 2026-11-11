"""Freeze weight-preserving harness comparison before diagnostic outputs."""
import time
from bt_common import ROOT,HERE,SOURCE,BS_ROOT,CONFIGS,sha,read,write,previous_check


def main():
    previous_check();assert not(ROOT/'frozen.json').exists()
    for name in ['runtime-smoke.json','decoder-smoke.json']:assert read(ROOT/name)['complete']
    policy={'optimizer_updates':0,'configs':CONFIGS,'diagnostic_order':list(CONFIGS),'max_actions':12,
       'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
       'Qwen_service_changes':False,'Q4_weights':True,'attention_math':'FP32','persistent_KV_precision':'per config',
       'selection':'diagnostic only; no loss in completions, repairs, correct finishes or first SPEC accuracy; no increase in accepted false DONE, false claims, corruptions or wrong-SPEC false DONE; ties favor baseline and simpler config',
       'challenger_audit':'If no candidate passes, preselect highest-ranked diagnostic challenger for research only; do not adopt it based on closed results.',
       'closed_goals':256,'closed_own_episodes':512,'closed_wrong_SPEC_episodes':64,'closed_gold_SPEC_episodes':64,
       'diagnostic_goals':64,'diagnostic_own_episodes':128,'diagnostic_wrong_SPEC_episodes':32,'diagnostic_gold_SPEC_episodes':32,
       'main_profile_replacement':False,'physical_device_access':False,'numeric_MATCH_is_not_intent_proof':True}
    write(ROOT/'policy.json',policy);data=read(ROOT/'data-frozen.json')
    for n,d in data['files'].items():assert sha(ROOT/n)==d,n
    files={**data['files'],**{n:sha(ROOT/n)for n in ['data-frozen.json','runtime-smoke.json','decoder-smoke.json','policy.json']}}
    sources={**read(BS_ROOT/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bt_*.py')},
             **{n:sha(HERE/n)for n in ['bs_resources.py','bs_model.py','capacity_verify.py']}}
    parent={str(p.relative_to(SOURCE)):sha(p)for p in [SOURCE/'model.mkqb',SOURCE/'model.mka',*sorted((SOURCE/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':files,'parent':parent,'optimizer_updates':0,
       'diagnostic_generations_seen':False,'closed_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'configs':CONFIGS,'files':len(files),'sources':len(sources)})
    print(read(ROOT/'prepared.json'))


if __name__=='__main__':main()
