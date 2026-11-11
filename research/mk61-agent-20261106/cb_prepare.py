"""Freeze actor adaptation, label consistency, zero-step Q4 parity and paired draws."""
import time
import torch
from cb_common import ROOT,HERE,ACTOR,read,write,rows,sha,previous_check,body_ids,output_ids,compact_head
from cb_model import Actor
from cb_course import Course,loss
from cb_runtime import render
from be_model import load
from bu_model import frozen_digest
from native_export import packet


def main():
    previous_check();assert not(ROOT/'frozen.json').exists();assert read(ROOT/'lessons-frozen.json')['complete']
    policy={'max_steps':1200,'checkpoints':[300,1200],'lr':1e-5,'weight_decay':.001,'warmup':25,'JS_weight':.05,'KD_weight':.2,
        'effective_batch':32,'microbatch':4,'accumulation':8,'data_seed':261127118,'model_seed':261127119,
        'context':1024,'training_tokens':1000,'maximum_target_tokens':160,'KV':'FP32','max_actions':12,'Q4_every_forward':True,
        'trainable_parameters':317440,'action_embeddings_frozen':True,'translator_frozen':'BU1500',
        'pair_formats':['full','notes'],'legacy_success_replay':True,'notes_only_long_states_explicit':True,
        'loss':'gold action CE +2 body CE +0.05 paired action JS +0.2 KD only teacher-correct predictions on successful replay',
        'mixture_pairs':{'matched_good_bad':6,'successful_replay':4,'run':2,'wrong_SPEC_diag':2,'unsure':1,'after_reject':1},
        'selection':'all original/full/notes development64 and retained-success32 cycles: no fewer completions/repairs/correct-start completions, no more accepted false DONE/corruption; notes development at least+2; no retained parent success lost',
        'selection_before_closed':True,'closed_used_for_selection':False,'visible_review_counter_same_in_parent_and_candidate':True,
        'legacy_no_counter_reference_also_measured':True,'main_profile_replacement':False,'physical_device_access':False,
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,'Qwen_service_changes':False}
    write(ROOT/'policy.json',policy)
    inputs={}
    for name in ['ast-frozen.json','teacher-frozen.json','lessons-frozen.json']:
        value=read(ROOT/name)
        for n,d in value['files'].items():assert sha(ROOT/n)==d,n
        inputs.update(value['files']);inputs[name]=sha(ROOT/name)
    model=Actor('cpu');model.save_checkpoint(ROOT/'initial.safetensors');packed,_=model.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(ACTOR/'model.mkqb')[1]
    teacher,tok=load(ACTOR,'cpu');compact_head(teacher,output_ids(tok));before=frozen_digest(model)
    course=Course(tok);batch=course.step(1,'cpu')[0];head=torch.tensor(body_ids(tok))
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,batch,head)
    value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    assert frozen_digest(model)==before and model.trainable_count()==317440
    used=[r for r in rows(ROOT/'lessons.jsonl')if r['state']['replan_attempted']]
    assert used and any(r['action']=='done'for r in used)and any(r['action']=='unsure'for r in used)
    for r in used[:100]:
        for f in ['full','notes']:assert 'Разборов SPEC осталось: 0.'in render(r['state'],f)
    course=Course(tok)
    for step in range(1,201):course.step(step,'cpu')
    proof={'complete':True,'optimizer_updates':0,'initial_actor_Q4_payload_exact':True,'finite_gradient':True,
        'loss':float(value.detach()),'parts':parts,'frozen_actor_digest':before,'teacher_digest':frozen_digest(teacher),
        'first200_draw_digest':course.digest,'first200_counts':dict(course.counts),'used_review_positive_and_negative_controls':True,
        'trainable_parameters':317440,'new_closed_goals':len(rows(ROOT/'closed.jsonl'))}
    write(ROOT/'CPU-preflight.json',proof)
    inputs.update({n:sha(ROOT/n)for n in ['policy.json','initial.safetensors','initial.mkqb','CPU-preflight.json']})
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('cb_*.py')if p.name not in ['cb_native.py','cb_finish.py','cb_pipeline.py']},
        'files':inputs,'closed_student_generations_seen':False,'SGD_started':False,'unix':time.time()})
    write(ROOT/'prepared.json',proof)
    p=HERE/'work-state.json';state=read(p);state.update(active_experiment='spec-actor-paired-formats-v1',all_own_jobs_complete=False,
        phase='paired_actor_prepared',latest_paired_actor_training={'phase':'prepared','optimizer_updates':0,'directory':str(ROOT),'ledger_accounted':False})
    write(p,state);print(proof,flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
