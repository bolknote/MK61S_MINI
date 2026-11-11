"""Freeze paired training, cumulative replay and full-cycle checkpoint selection."""
import time
import json
import torch
from bx_common import ROOT,HERE,BU_ROOT,BV_ROOT,ACTOR,PARENT,PARENT_CHECKPOINT,read,write,rows,sha,previous_check,body_ids,output_ids,compact_head
from bx_course import Course,loss,training_pool
from bu_model import Translator,frozen_digest
from be_model import load
from native_export import packet
from be_language import paths3
from az_data import numbers
from ay_codec import compile_spec
from ha_protocol import assemble


def main():
    previous_check();assert not(ROOT/'frozen.json').exists()
    ast=read(ROOT/'ast-frozen.json');wording_info=read(ROOT/'teacher-frozen.json')
    for group in [ast['files'],wording_info['files']]:
        for n,d in group.items():assert sha(ROOT/n)==d,n
    held={tuple(v)for values in ast['held_triples'].values()for v in values}
    assert not(set(map(tuple,ast['held_triples']['development']))&set(map(tuple,ast['held_triples']['closed'])))
    policy={'max_steps':1200,'checkpoints':[200,600,1200],'stop_at_first_protected_improvement':True,
        'lr':1e-5,'weight_decay':.001,'JS_weight':.1,'KD_weight':.25,'effective_batch':32,'microbatch':4,'accumulation':8,
        'data_seed':261126118,'model_seed':261126119,'context':1024,'KV':'FP32','Q4_every_forward':True,'trainable_parameters':317440,
        'batch_pairs':{'exact_hard':2,'cumulative_regressions':2,'matched_contrast_goals':4,'retained_successes':3,'composition_successes':3,'general_replay':1,'new_expression':1},
        'pair':'same task, literal pool, target and layout; initial remaining12 and code-free replan remaining3..11',
        'loss':'gold CE on both phases +0.1 JS between aligned distributions +0.25 correct-token KD on verified successes only',
        'cumulative_replay':'one current error and one historical error; history is union-only, no corrected item removed',
        'selection':'every checkpoint gets full development cycles and unconditional paired probes, even when fit controls fail; first all-gates checkpoint with at least2 more completions',
        'closed_used_for_selection':False,'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,
        'Qwen_service_changes':False,'main_profile_replacement':False,'physical_device_access':False,'max_actions':12,
        'initial_parent':'BU1500','actor_unchanged':True,'development_goals':128,'closed_goals':256,'closed_composition_families':32}
    write(ROOT/'policy.json',policy)
    pool_proof=0
    for g in rows(ROOT/'train.jsonl'):
        normalized=training_pool(g)
        assert assemble(compile_spec(g['spec'],normalized),normalized,'asm')==assemble(g['reference_body'],g['pool'],'asm')
        pool_proof+=1
    write(ROOT/'pool-order-proof.json',{'checked':pool_proof,'canonical_base_prefix':True,'compiled_ROM_programs_unchanged':True,'raw_teacher_data_unchanged':True})
    labels={}
    for file in ['hard.jsonl','regressions.jsonl','anchors.jsonl','train.jsonl']:
        for g in rows(ROOT/file):
            assert not paths3(g['spec']['X'])&held and not numbers(g['spec']['X'])&set(ast['fresh_dev_literals']+ast['fresh_test_literals'])
            key=(g['spec']['angle'],g['task']);value=json.dumps(g['spec'],sort_keys=True,ensure_ascii=False)
            if key in labels:assert labels[key]==value,('conflicting_priority_labels',g['id'])
            labels[key]=value
    valid=[];excluded=[]
    for i,g in enumerate(rows(ROOT/'general.jsonl')):
        assert not paths3(g['spec']['X'])&held and not numbers(g['spec']['X'])&set(ast['fresh_dev_literals']+ast['fresh_test_literals'])
        key=(g['spec']['angle'],g['task'])
        if key in labels and labels[key]!=json.dumps(g['spec'],sort_keys=True,ensure_ascii=False):excluded.append(i)
        else:valid.append(i)
    write(ROOT/'general-valid-ids.json',valid);write(ROOT/'label-and-leakage-check.json',{'general_excluded':excluded,'held_paths_and_numbers_excluded':True})
    parent_fit=read(BV_ROOT/'parent-fit.json');write(ROOT/'parent-fit.json',parent_fit)
    model=Translator('cpu',PARENT_CHECKPOINT);model.save_checkpoint(ROOT/'initial.safetensors');packed,_=model.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(PARENT/'model.mkqb')[1]
    teacher,tok=load(PARENT,'cpu');compact_head(teacher,output_ids(tok));before=frozen_digest(model)
    course=Course(tok);head=torch.tensor(body_ids(tok))
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,course.step(1,'cpu')[0],head,policy['JS_weight'],policy['KD_weight'])
    value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    assert frozen_digest(model)==before and model.trainable_count()==317440
    history=set(course.cumulative);empty={'hard':{'records':[]},'retention':{'records':[]},'composition':{'records':[]}}
    course.prioritize(empty,0);assert history==course.cumulative
    # A paired target is identical despite different prefix and remaining budget.
    course=Course(tok)
    for step in range(1,201):course.step(step,'cpu')
    proof={'complete':True,'optimizer_updates':0,'initial_Q4_payload_equals_BU1500':True,'finite_gradient':True,'loss':float(value.detach()),'parts':parts,
        'frozen_translator_digest':before,'first200_draw_digest':course.digest,'first200_counts':dict(course.counts),'initial_cumulative_count':len(course.cumulative),'corrected_history_retained':True}
    write(ROOT/'CPU-preflight.json',proof)
    files={**ast['files'],**wording_info['files'],**{n:sha(ROOT/n)for n in ['ast-frozen.json','teacher-frozen.json','policy.json','pool-order-proof.json','general-valid-ids.json','label-and-leakage-check.json','parent-fit.json','initial.safetensors','initial.mkqb','CPU-preflight.json']}}
    from bw_common import ROOT as BW_ROOT
    sources={**read(BW_ROOT/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bx_*.py')if p.name not in ['bx_native.py','bx_finish.py']}}
    write(ROOT/'frozen.json',{'files':files,'sources':sources,'parent_adapter_sha256':sha(PARENT_CHECKPOINT),'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',proof)
    s=read(HERE/'work-state.json');s.update(active_experiment='spec-phase-consistency-v1',all_own_jobs_complete=False,phase='spec_phase_consistency_prepared',
        latest_phase_consistency_training={'phase':'prepared','optimizer_updates':0,'parent':'BU1500','directory':str(ROOT),'actor_unchanged':True,'ledger_accounted':False})
    write(HERE/'work-state.json',s);print(proof,flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
