"""Freeze source and prove exact continuation of the already selected Q4 adapter."""
import json
import hashlib
import shutil
import torch
from aj_common import ROOT,HERE,PARENT,START,START_PACKET,TEACHERS,INITIAL_PACKET,COMPILER_PACKET,read,write,sha,body_ids,output_ids,compact_head
from aj_model import Agent
from aj_course import Course,loss,frozen_teachers,distillation_loss
from aj_eval import generate
from aj_teacher import make_session,correct
from full_isa_vm import FullVM
from native_export import packet


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(START)==frozen['start_checkpoint_sha256']and sha(START_PACKET)==frozen['start_packet_sha256']
    assert sha(INITIAL_PACKET)==frozen['initial_tool_packet_sha256']and sha(COMPILER_PACKET)==frozen['compiler_packet_sha256']
    for name,(folder,p)in TEACHERS.items():
        assert sha(folder/'model.safetensors')==frozen['teachers'][name]['master_sha256']
        assert sha(p)==frozen['teachers'][name]['packet_sha256']
    torch.set_num_threads(4);torch.manual_seed(913501);torch.cuda.set_per_process_memory_fraction(.8);torch.backends.cuda.matmul.allow_tf32=False
    for name in ['lessons.jsonl','hard-lessons.jsonl','completion.jsonl','retention.jsonl','anchors.jsonl']:
        assert all(r['correctness']and r['eligible_for_DONE']for r in read(ROOT/name)if r['action']=='done'),name
    train=read(ROOT/'train.jsonl');train_keys={(t['angle'],t['task'])for t in train};dev=read(ROOT/'development.jsonl')+read(ROOT/'development-goals.jsonl')+read(ROOT/'development-skills.jsonl');fresh=read(ROOT/'fresh.jsonl')+read(ROOT/'fresh-goals.jsonl')+read(ROOT/'fresh-skills.jsonl')
    assert not(train_keys&{(t['angle'],t['task'])for t in dev+fresh})
    assert not({(t['angle'],t['task'])for t in dev}&{(t['angle'],t['task'])for t in fresh})
    vm=FullVM();lookup={t['id']:t for t in train};matched={}
    for seed in read(ROOT/'train-seeds.jsonl')[:128]:
        s=make_session(lookup[seed['task_id']],seed,vm)
        assert not({'hidden_tests','reference_code'}&set(s.task));assert all('expected'not in x for c in s.task['public_tests']for x in c['segments'])
        if not seed.get('start_empty'):assert correct(vm,lookup[seed['task_id']],s.body,s.pool)==seed['intentionally_correct']
        sig=tuple(str(seed.get(k))for k in ['pool','prefill_revision','pre_run_all','trace_before','critic_warning','error_probe'])
        if seed['pair_id']in matched:assert matched[seed['pair_id']]==sig
        matched[seed['pair_id']]=sig
    model=Agent('lr20');before=model.input_digest();packed,_=model.packed(ROOT/'preflight.mkqb');assert packet(ROOT/'preflight.mkqb')[1]==packet(START_PACKET)[1]
    packed.cuda().eval();compact_head(packed,output_ids(model.tokenizer));dl={t['id']:t for t in dev}
    for name in model.adapter_names:
        assert torch.equal(model.base.get_submodule(name).weight.detach(),packed.get_parameter(name+'.weight')),name
    prompts=[make_session(dl[s['task_id']],s,vm).request()for s in read(ROOT/'development-seeds.jsonl')[:8]]
    a=generate(model,model.tokenizer,prompts);b=generate(packed,model.tokenizer,prompts)
    assert[r['generated_token_ids']for r in a]==[r['generated_token_ids']for r in b]
    error=max(abs(x['correctness_margin']-y['correctness_margin'])for x,y in zip(a,b));assert error<1e-4,error
    policy=json.loads((ROOT/'policy.json').read_text());course=Course(model.tokenizer,1);batch,anchors=course.batch(0,'cuda')
    probe=Course(model.tokenizer,1);run_cases=[]
    for _ in range(128):
        source,index,_=probe.draw('hard','run');run_cases.append(probe.rows[source][index]['body'][0])
    assert set(run_cases)=={0,1,2,3},set(run_cases)
    assert len(batch[0])==policy['batch']and all(len(a[0])==policy['anchor_batch_per_teacher']for a in anchors.values())
    teachers=frozen_teachers();head=torch.tensor(body_ids(model.tokenizer),device='cuda')
    def digest(m):
        h=hashlib.sha256()
        for p in m.parameters():h.update(p.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()
    teacher_before={n:digest(m)for n,m in teachers.items()}
    with torch.no_grad(),torch.nn.utils.parametrize.cached():
        keep0,_=distillation_loss(model,{'distill':teachers['distill']},anchors,head,policy)
    assert float(keep0)<1e-5,float(keep0)
    original_head=model.action_head.detach().clone()
    with torch.no_grad():model.action_head.add_(torch.randn_like(model.action_head)*.1)
    with torch.no_grad(),torch.nn.utils.parametrize.cached():
        changed,_=distillation_loss(model,{'distill':teachers['distill']},anchors,head,policy)
    assert float(changed)>float(keep0)+1e-4,(float(keep0),float(changed))
    with torch.no_grad():model.action_head.copy_(original_head)
    model.train()
    with torch.nn.utils.parametrize.cached(),torch.autocast('cuda',dtype=torch.bfloat16):
        value,parts=loss(model,batch,head,policy)
        keep,details=distillation_loss(model,teachers,anchors,head,policy)
        value=value+policy['distill_weight']*keep
    assert torch.isfinite(value)and parts['loop_exit_rows']>=16
    value.backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters())
    assert model.correct_head.grad is not None and model.action_head.grad is not None
    assert any(p.grad is not None and p.grad.abs().sum()>0 for n,p in model.named_parameters()if'parametrizations'in n)
    assert model.input_digest()==before
    assert all(p.grad is None for teacher in teachers.values()for p in teacher.parameters())
    assert{n:digest(m)for n,m in teachers.items()}==teacher_before
    excluded={'aj_remote.py','aj_collect.py','aj_export.py','aj_native.py','aj_verify.py','aj_report.py','aj_chat.py','aj_demos.py'}
    names=[p.name for p in HERE.glob('aj_*.py')if p.name not in excluded]
    parent=json.loads((PARENT/'prepared.json').read_text())
    for name,d in parent['source_hashes'].items():assert sha(HERE/name)==d,name
    names+=list(parent['source_hashes'])+['ah_common.py','ah_data.py','run_experiment.py','lowbit.py','tasks.py','ha_data.py','hr_data.py','full_isa_prepare.py','full_isa_protocol.py','natural_data.py']
    names=sorted(set(names))
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for name in names:shutil.copyfile(HERE/name,source/name)
    files={str(p.relative_to(ROOT)):sha(p)for p in list(source.iterdir())+list((ROOT/'core-source').rglob('*'))if p.is_file()}
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':files,
        'trainable_parameters':model.trainable_count(),'start_Q4_payload_bit_identical':True,'start_merge_streams_equal':True,'margin_max_error':error,
        'new_losses_have_finite_gradients':True,'input_embedding_digest':before,'all_DONE_labels_true_and_eligible':True,
        'frozen_teacher_unchanged_and_no_gradients':True,'KL_at_identical_start':float(keep0),'KL_after_temporary_perturbation':float(changed),
        'training_batch':len(batch[0]),'anchor_batches':{n:len(a[0])for n,a in anchors.items()},'loop_exit_margin_finite':True,
        'RUN_sampling_all_valid_cases_verified':sorted(set(run_cases)),
        'CUDA_forward_adapted_matrices_bit_equal_CPU_export':True,'rounding_fixed_before_any_optimizer_updates':True,
        'preflight_optimizer_updates':0,'runtime_has_no_expected_hidden_reference':True,'fresh_used_for_selection':False})
    print(json.dumps({'preflight':'passed','trainable':model.trainable_count(),'margin_error':error}),flush=True)


if __name__=='__main__':main()

