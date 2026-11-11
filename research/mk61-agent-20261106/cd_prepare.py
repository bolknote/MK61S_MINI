"""Freeze actual-utility labeling, a single-row QAT gate and an untouched new test."""
import time
import torch
from cd_common import ROOT,HERE,ACTOR,PARENT,WORKING,read,write,rows,sha,previous_check,ACTION_IDS,body_ids
from cd_model import Actor,ROWS
from cd_rollout import OTHER
from aq_protocol import prompt_ids,header_ids
from native_export import packet
from bu_model import frozen_digest

def main():
    previous_check();assert not(ROOT/'frozen.json').exists();assert read(ROOT/'cases-frozen.json')['complete']
    policy={'max_steps':800,'checkpoints':[200,800],'lr':1e-4,'weight_decay':.001,'warmup':20,'KD_weight':4.,'L2_weight':.1,
        'effective_batch':128,'data_seed':261129118,'context':1024,'KV':'FP32','Q4_every_trainable_forward':True,
        'trainable_parameters':128,'trainable_actions':['diag'],'frozen_other_five_action_rows':True,'frozen_encoder':True,'frozen_body_decoder':True,
        'training':'CPU FP32 AdamW on cached frozen Q4 features; binary gate BCE versus max frozen non-DIAG logit',
        'runtime':'unchanged legacy prompt, BU1500 translator, six actions and gate; only DIAG readout may change',
        'minimum_utility_cases':448,'minimum_review_positives':32,'minimum_nonreview_labels':64,
        'counterfactual':'same reconstructed training state; force real actor DIAG body or highest frozen non-DIAG action; ordinary frozen actor and real BU1500 replan afterward; remaining budget12 includes prefix',
        'utility_labels':'DIAG only if actual review enables successful completion or prevents wrong WRITE; ties prefer non-DIAG; both failed are unlabelled except measured harm to existing correct code',
        'batch':'8 useful reviews,24 measured nonreviews,64 verified successful nonreview anchors,16 successful repair anchors,16 correct DONE anchors',
        'loss':'binary gate BCE +4 verified-success action KL +0.1 head L2; no global DONE penalty',
        'selection':'dev64 and parent-success48: no worse completion/repair/correct finishes than controls; no more accepted false DONE/corruption/false-claim episodes/wrong WRITE on correct starts; no individual retained success lost; improvement over parent required',
        'closed_tasks':256,'closed_composition_families':32,'max_actions':12,'selection_before_closed':True,'closed_used_for_selection':False,
        'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,'gpu':0,'host_gpu':1,'Qwen_service_changes':False,
        'main_profile_replacement':False,'physical_device_access':False}
    write(ROOT/'policy.json',policy);inputs={}
    for name in ['ast-frozen.json','teacher-frozen.json','cases-frozen.json']:
        info=read(ROOT/name)
        for n,d in info['files'].items():assert sha(ROOT/n)==d,n
        inputs.update(info['files']);inputs[name]=sha(ROOT/name)
    for folder in [ACTOR,WORKING,PARENT]:
        for p in folder.rglob('*'):
            if p.is_file():inputs[str(p.relative_to(ROOT))]=sha(p)
    model=Actor('cpu');before=frozen_digest(model);model.save_checkpoint(ROOT/'initial.safetensors');packed,_=model.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(ACTOR/'model.mkqb')[1]
    tok=model.tokenizer;assert not set(ACTION_IDS)&set(body_ids(tok))and all(not set(ACTION_IDS)&set(header_ids(tok,a))for a in ['write','run','diag'])
    assert all(not set(prompt_ids(tok,s['prompt']))&set(ACTION_IDS)for s in rows(ROOT/'utility-seeds.jsonl'))
    h=torch.randn(8,128,generator=torch.Generator().manual_seed(261129119));logits=torch.nn.functional.linear(h,model.action_weight())
    margin=logits[:,ROWS[0]]-logits[:,OTHER].max(-1).values;value=torch.nn.functional.binary_cross_entropy_with_logits(margin,torch.tensor([0.,1.,0.,1.,0.,1.,0.,1.]));value.backward()
    assert torch.isfinite(value)and model.decision_head.grad is not None and model.decision_head.grad.abs().sum()>0
    assert all(p.grad is None for n,p in model.named_parameters()if n!='decision_head')and frozen_digest(model)==before
    proof={'complete':True,'optimizer_updates':0,'initial_parent_Q4_payload_exact':True,'finite_gate_gradient':True,'trainable_parameters':128,
        'frozen_body_and_other_action_digest':before,'action_rows_absent_from_inputs_and_body_grammar':True,'no_runtime_fields_added':True,
        'paired_seeds':len(rows(ROOT/'utility-seeds.jsonl')),'utility_labels_not_generated_yet':True}
    write(ROOT/'CPU-preflight.json',proof);inputs.update({n:sha(ROOT/n)for n in ['policy.json','initial.safetensors','initial.mkqb','CPU-preflight.json']})
    excluded={'cd_native.py','cd_finish.py','cd_pipeline.py'}
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('cd_*.py')if p.name not in excluded},'files':inputs,
        'SGD_started':False,'closed_student_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',proof)
    state=read(HERE/'work-state.json');state.update(active_experiment='spec-review-utility-v1',all_own_jobs_complete=False,phase='review_utility_prepared',
        latest_review_utility_training={'phase':'prepared','directory':str(ROOT),'optimizer_updates':0,'ledger_accounted':False})
    write(HERE/'work-state.json',state);print(proof,flush=True)

if __name__=='__main__':torch.set_num_threads(3);main()
