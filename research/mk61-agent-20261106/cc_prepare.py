"""Freeze task partitions, narrow action training and all comparisons before SGD."""
import time
import torch
from cc_common import ROOT,HERE,ACTOR,PARENT,WORKING,read,write,rows,sha,previous_check,ACTION_IDS,ACTIONS,body_ids
from cc_model import Actor,ROWS
from cc_course import Course
from aq_protocol import prompt_ids,header_ids
from native_export import packet
from bu_model import frozen_digest

def main():
    previous_check();assert not(ROOT/'frozen.json').exists();assert read(ROOT/'lessons-frozen.json')['complete']
    policy={'max_steps':800,'checkpoints':[200,800],'lr':2e-4,'weight_decay':.001,'warmup':20,'KD_weight':2.,'L2_weight':.05,
        'effective_batch':128,'data_seed':261128118,'context':1024,'KV':'FP32','Q4_every_trainable_forward':True,
        'trainable_parameters':384,'trainable_actions':['write','done','diag'],'frozen_encoder':True,'frozen_body_decoder':True,
        'training':'FP32 CPU AdamW on cached frozen Q4 B200 hidden states; Q4 readout each forward',
        'runtime':'unchanged legacy prompt, BU1500 translator, body decoder and gate; no new visible counter',
        'selection':'new dev64 and retired-success48: no worse completion/repair/correct finishes than either parent or working; false DONE/corruption/false-claim episodes no worse than either; no individual retention success lost; improvement over parent required',
        'loss':'balanced four-way gold action CE +2 verified successful-action KL +0.05 head L2; no body updates or global DONE penalty',
        'closed_tasks':256,'closed_composition_families':32,'max_actions':12,'selection_before_closed':True,'closed_used_for_selection':False,
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,'Qwen_service_changes':False,
        'main_profile_replacement':False,'physical_device_access':False}
    write(ROOT/'policy.json',policy);inputs={}
    for name in ['ast-frozen.json','teacher-frozen.json','lessons-frozen.json']:
        info=read(ROOT/name)
        for n,d in info['files'].items():assert sha(ROOT/n)==d,n
        inputs.update(info['files']);inputs[name]=sha(ROOT/name)
    for folder in [ACTOR,WORKING,PARENT]:
        for p in folder.rglob('*'):
            if p.is_file():inputs[str(p.relative_to(ROOT))]=sha(p)
    model=Actor('cpu');before=frozen_digest(model);model.save_checkpoint(ROOT/'initial.safetensors');replica,_=model.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(ACTOR/'model.mkqb')[1]
    tok=model.tokenizer;assert not set(ACTION_IDS)&set(body_ids(tok))
    assert all(not set(ACTION_IDS)&set(header_ids(tok,a))for a in ['write','run','diag'])
    data=rows(ROOT/'lessons.jsonl');assert not any(set(prompt_ids(tok,r['prompt']))&set(ACTION_IDS)for r in data)
    hidden=torch.randn(8,128,generator=torch.Generator().manual_seed(261128119));logits=torch.nn.functional.linear(hidden,model.action_weight())
    value=torch.nn.functional.cross_entropy(logits,torch.tensor([0,3,5,0,3,5,1,4]));value.backward()
    assert torch.isfinite(value)and model.decision_head.grad is not None and model.decision_head.grad.abs().sum()>0
    assert all(p.grad is None for n,p in model.named_parameters()if n!='decision_head')and frozen_digest(model)==before
    course=Course()
    for step in range(1,201):course.draw(step)
    proof={'complete':True,'optimizer_updates':0,'initial_parent_Q4_payload_exact':True,'finite_head_gradient':True,'trainable_parameters':384,
        'frozen_body_digest':before,'first200_draw_digest':course.digest,'first200_counts':dict(course.counts),
        'action_rows_absent_from_all_training_inputs_and_body_grammar':True,'no_new_runtime_fields':True,'states':len(data)}
    write(ROOT/'CPU-preflight.json',proof)
    inputs.update({n:sha(ROOT/n)for n in ['policy.json','initial.safetensors','initial.mkqb','CPU-preflight.json']})
    excluded={'cc_native.py','cc_finish.py','cc_pipeline.py'}
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('cc_*.py')if p.name not in excluded},'files':inputs,
        'SGD_started':False,'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',proof)
    state=read(HERE/'work-state.json');state.update(active_experiment='spec-action-choice-v1',all_own_jobs_complete=False,phase='action_choice_prepared',
        latest_action_choice_training={'phase':'prepared','directory':str(ROOT),'optimizer_updates':0,'ledger_accounted':False})
    write(HERE/'work-state.json',state);print(proof,flush=True)

if __name__=='__main__':torch.set_num_threads(3);main()
