"""Freeze targeted repair, verified replay, first-safe stopping, and sealed test."""
import copy
import json
import time
import torch
from bv_common import ROOT,HERE,BU_ROOT,PARENT,PARENT_CHECKPOINT,read,write,rows,sha,previous_check,body_ids,output_ids,compact_head
from bu_model import Translator,frozen_digest,actor
from be_model import load
from bv_course import Course,loss
from bv_eval import ActorCache
from bj_runtime import render
from ay_runtime import goal_state
from ay_eval import primary_metrics
from bt_decode import generate
from bu_eval import CONFIG
from be_language import paths3
from az_data import numbers
from native_export import packet


def parent_fit():
    v=read(BU_ROOT/'server-results/development-1500.json');ret={r['id']:r for r in v['retention']['records']}
    primary={r['id']:r for name in ['closed-final','development-1500']for r in read(BU_ROOT/'server-results'/(name+'.json'))['primary']['records']}
    result={'split':'fit','fit_controls_not_independent':True,'reused_exact_BU_Q4_generation_records':True}
    for name,file,lookup in [('hard','hard.jsonl',{**ret,**primary}),('retention','retention.jsonl',ret),('composition','composition-regression.jsonl',primary)]:
        records=[]
        for g in rows(ROOT/file):
            r=copy.deepcopy(lookup[g.get('source_id',g['id'])]);assert r['prompt']==render(goal_state(g),'spec'),g['id'];r['id']=g['id'];records.append(r)
        result[name]={'summary':primary_metrics(records),'records':records}
    return result


def main():
    previous_check();assert not(ROOT/'frozen.json').exists();ast=read(ROOT/'ast-frozen.json');teacher_info=read(ROOT/'teacher-frozen.json');preflight=read(ROOT/'GPU-preflight.json')
    assert preflight['complete']and preflight['optimizer_updates']==0 and preflight['peak_reserved_MiB']<=1536
    for group in [ast['files'],teacher_info['files']]:
        for n,d in group.items():assert sha(ROOT/n)==d,n
    policy={'max_steps':2400,'checkpoints':[200,600,1200,2400],'stop_at_first_protected_checkpoint':True,
       'lr':2e-5,'weight_decay':.001,'KD_weight':.5,'effective_batch':32,'microbatch':preflight['microbatch'],'accumulation':32//preflight['microbatch'],
       'data_seed':261124118,'model_seed':261124119,'context':1024,'KV':'FP32','Q4_every_forward':True,'trainable_parameters':317440,
       'routing':'unchanged BU routing: translator only for forced initial/replan WRITE; all ordinary calls and bodies use immutable actor',
       'batch':'4 exact repairs;4 repair paraphrases;8 verified retention;8 verified compositions;8 general replay (up to4 replaced by known training-fit errors after a checkpoint)',
       'KD':'only verified parent successes; copy a token only when teacher argmax agrees with its verified target; no KD on nine errors or variants',
       'priority_updates_use_only_retired_training_fit_panels':True,'fit_gate':'nine originals and extra cosine all correct; zero loss among102 parent retention successes and185 parent composition successes',
       'selection':'first fit-safe checkpoint with no worse new-development SPEC, completions, repairs, correct finishes, false DONE, corruption, false-claim episodes, wrong-SPEC false DONE',
       'closed_used_for_selection':False,'max_actions':12,'closed_goals':256,'closed_composition_families':32,
       'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,'Qwen_service_changes':False,
       'main_profile_replacement':False,'physical_device_access':False}
    write(ROOT/'policy.json',policy);held={tuple(x)for x in ast['all_training_excluded_triples']};labels={}
    for g in rows(ROOT/'hard.jsonl')+rows(ROOT/'anchors.jsonl')+rows(ROOT/'train.jsonl'):
        key=(g['spec']['angle'],g['task']);value=json.dumps(g['spec'],sort_keys=True,ensure_ascii=False)
        assert key not in labels or labels[key]==value,('conflicting_repair_labels',g['id']);labels[key]=value
        assert not paths3(g['spec']['X'])&held
        assert not numbers(g['spec']['X'])&set(DEVTEST:=ast['fresh_dev_literals']+ast['fresh_test_literals'])
    valid=[];skipped=[]
    for i,g in enumerate(rows(ROOT/'general.jsonl')):
        key=(g['spec']['angle'],g['task']);value=json.dumps(g['spec'],sort_keys=True,ensure_ascii=False)
        if key in labels and labels[key]!=value:skipped.append(i);continue
        assert not paths3(g['spec']['X'])&held and not numbers(g['spec']['X'])&set(DEVTEST)
        valid.append(i)
    write(ROOT/'general-valid-ids.json',valid);write(ROOT/'leakage-and-label-check.json',{'valid_general':len(valid),'conflicting_general_excluded':skipped,'closed_paths_and_literals_excluded':True})
    a=Translator('cpu',PARENT_CHECKPOINT);a.save_checkpoint(ROOT/'initial.safetensors');replica,_=a.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(PARENT/'model.mkqb')[1];assert a.trainable_count()==317440;del replica
    teacher,tok=load(PARENT,'cpu');compact_head(teacher,output_ids(tok));fit=parent_fit();parity=[]
    for mode in ['hard','retention','composition']:
        r=next(v for v in fit[mode]['records']if not v['generation'].get('codec_error'))
        cpu=generate(teacher,tok,[r['prompt']],CONFIG,'write')[0]
        assert cpu['generated_token_ids']==r['generation']['generated_token_ids']
        parity.append({'mode':mode,'id':r['id'],'saved_B200_equals_CPU':True})
    write(ROOT/'parent-fit.json',fit)
    before=frozen_digest(a);course=Course(a.tokenizer);head=torch.tensor(body_ids(a.tokenizer))
    with torch.nn.utils.parametrize.cached():value,parts=loss(a,teacher,course.step(1,'cpu')[0],head,policy['KD_weight'])
    value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in a.parameters()if p.grad is not None);assert frozen_digest(a)==before
    frozen,_=actor('cpu');cache=ActorCache();record=read(BU_ROOT/'server-results/closed-final.json')['own']['records']
    h=next(h for r in record for h in r['history']if h.get('generation',{}).get('profile')=='unchanged_actor'and not h['generation'].get('codec_error'))
    x=cache.generate(frozen,tok,h['prompt']);y=cache.generate(frozen,tok,h['prompt']);assert x['generated_token_ids']==y['generated_token_ids']==h['generation']['generated_token_ids']and y['actor_cache_hit']
    write(ROOT/'router-and-cache-check.json',{'complete':True,'reused_parent_fit_parity':parity,'same_prompt_same_actor_cache_equals_fresh':True,'closed_student_generations_seen':False})
    course=Course(a.tokenizer)
    for step in range(1,201):course.step(step,'cpu')
    files={**ast['files'],**teacher_info['files'],**{n:sha(ROOT/n)for n in ['ast-frozen.json','teacher-frozen.json','teacher-audit.jsonl','policy.json','initial.safetensors','initial.mkqb','parent-smoke.json','GPU-preflight.json','parent-fit.json','router-and-cache-check.json','general-valid-ids.json','leakage-and-label-check.json']}}
    sources={**read(BU_ROOT/'inputs-frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bv_*.py')if p.name not in ['bv_native.py','bv_finish.py']}}
    parent={str(p.relative_to(PARENT)):sha(p)for p in [PARENT/'model.mkqb',PARENT/'manifest.json',*sorted((PARENT/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'files':files,'sources':sources,'parent':parent,'parent_adapter_sha256':sha(PARENT_CHECKPOINT),'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'initial_payload_equals_BU1500':True,'trainable_parameters':317440,'frozen_translator_digest':before,
       'finite_gradient':True,'loss':float(value.detach()),'parts':parts,'first200_draw_digest':course.digest,'first200_counts':dict(course.counts)})
    print(read(ROOT/'prepared.json'),flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
