"""Freeze source and prove exact continuation of the already selected Q4 adapter."""
import json
import shutil
import torch
from af_common import ROOT,HERE,START,START_PACKET,INITIAL_PACKET,COMPILER_PACKET,read,write,sha,body_ids,output_ids,compact_head
from af_model import Agent
from af_course import Course,loss,pair_loss
from af_eval import generate
from af_teacher import make_session,correct
from full_isa_vm import FullVM
from native_export import packet


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(START)==frozen['start_checkpoint_sha256']and sha(START_PACKET)==frozen['start_packet_sha256']
    assert sha(INITIAL_PACKET)==frozen['initial_tool_packet_sha256']and sha(COMPILER_PACKET)==frozen['compiler_packet_sha256']
    torch.set_num_threads(4);torch.manual_seed(913501);torch.cuda.set_per_process_memory_fraction(.8);torch.backends.cuda.matmul.allow_tf32=False
    lessons=read(ROOT/'lessons.jsonl');assert all(r['correctness']and r['eligible_for_DONE']for r in lessons if r['action']=='done')
    train=read(ROOT/'train.jsonl');train_keys={(t['angle'],t['task'])for t in train};dev=read(ROOT/'development.jsonl')+read(ROOT/'development-goals.jsonl');fresh=read(ROOT/'fresh.jsonl')+read(ROOT/'fresh-goals.jsonl')
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
    model=Agent('replay');before=model.input_digest();packed,_=model.packed(ROOT/'preflight.mkqb');assert packet(ROOT/'preflight.mkqb')[1]==packet(START_PACKET)[1]
    packed.cuda().eval();compact_head(packed,output_ids(model.tokenizer));dl={t['id']:t for t in dev}
    for name in model.adapter_names:
        assert torch.equal(model.base.get_submodule(name).weight.detach(),packed.get_parameter(name+'.weight')),name
    prompts=[make_session(dl[s['task_id']],s,vm).request()for s in read(ROOT/'development-seeds.jsonl')[:8]]
    a=generate(model,model.tokenizer,prompts);b=generate(packed,model.tokenizer,prompts)
    assert[r['generated_token_ids']for r in a]==[r['generated_token_ids']for r in b]
    error=max(abs(x['correctness_margin']-y['correctness_margin'])for x,y in zip(a,b));assert error<1e-4,error
    policy=json.loads((ROOT/'policy.json').read_text());course=Course(model.tokenizer,1);batch,pairs=course.batch(0,'cuda')
    value,parts=loss(model,batch,torch.tensor(body_ids(model.tokenizer),device='cuda'),policy);contrast,cp=pair_loss(model,pairs,policy)
    (value+policy['pair_weight']*contrast).backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters())
    assert model.correct_head.grad is not None and model.action_head.grad is not None
    assert any(p.grad is not None and p.grad.abs().sum()>0 for n,p in model.named_parameters()if'parametrizations'in n)
    assert model.input_digest()==before
    excluded={'af_remote.py','af_collect.py','af_export.py','af_native.py','af_verify.py','af_report.py','af_chat.py','af_demos.py'}
    names=[p.name for p in HERE.glob('af_*.py')if p.name not in excluded]
    names+=['ae_common.py','ae_model.py','ae_teacher.py','ae_data.py','ac_common.py','ac_protocol.py','ac_runtime.py','ac_model.py','ac_course.py','ac_eval.py','ab_eval.py','hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_vm.py','full_isa_math.py','native_quant.py','quantization.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for name in names:shutil.copyfile(HERE/name,source/name)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()},
        'trainable_parameters':model.trainable_count(),'start_Q4_payload_bit_identical':True,'start_merge_streams_equal':True,'margin_max_error':error,
        'new_losses_have_finite_gradients':True,'input_embedding_digest':before,'all_DONE_labels_true_and_eligible':True,
        'CUDA_forward_adapted_matrices_bit_equal_CPU_export':True,'rounding_fixed_before_any_optimizer_updates':True,
        'preflight_optimizer_updates':0,'runtime_has_no_expected_hidden_reference':True,'fresh_used_for_selection':False})
    print(json.dumps({'preflight':'passed','trainable':model.trainable_count(),'margin_error':error}),flush=True)


if __name__=='__main__':main()

