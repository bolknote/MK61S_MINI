"""Pre-SGD checks for frozen-base identity and argument-sensitive preferences."""
import copy
import json
import math
import shutil
import tempfile
from pathlib import Path
import torch
from ac_common import ROOT,HERE,INITIAL,INITIAL_PACKET,read,write,sha,body_ids,output_ids,compact_head
from ac_model import Agent
from ac_course import encoded,pad,supervised_loss,trajectory_dpo
from ac_eval import generate,compiler_model,compiler_evaluate
from ac_teacher import make_session
from ac_runtime import Session
from full_isa_vm import FullVM
from ab_prepare import PublicOnly


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    torch.set_num_threads(4);torch.manual_seed(811412);torch.cuda.set_per_process_memory_fraction(.8)
    model=Agent();tokenizer=model.tokenizer;original=model.frozen_digest();vm=FullVM()
    tasks=read(ROOT/'validation.jsonl');lookup={t['id']:t for t in tasks};items=read(ROOT/'validation-seeds.jsonl')
    sessions=[make_session(lookup[i['task_id']],i,vm)for i in items[:8]]
    # Trap any access to an oracle during real execution or request construction.
    t=PublicOnly(copy.deepcopy(tasks[0]));t['public_tests']=[{'segments':[PublicOnly(s)for s in c['segments']]}for c in t['public_tests']]
    s=Session(t,'asm',body=sessions[0].body,vm=vm,gate=False);s.run(0);s.request();s.apply_action('trace',[]);s.request()
    assert s.apply_action('unsure',[])=='unsure'and not s.finished
    # The action is identical in both branches. Only a program byte differs.
    question=sessions[0].request()
    good={'prompt':question,'action':'write','body':[0x1C,0x50]}
    bad={'prompt':question,'action':'write','body':[0x1D,0x50]}
    batch=pad(tokenizer,[encoded(tokenizer,good),encoded(tokenizer,bad)],'cuda');head=torch.tensor(body_ids(tokenizer),device='cuda')
    with tempfile.TemporaryDirectory()as tmp:
        checkpoint=Path(tmp)/'adapter.safetensors';model.save_adapter(checkpoint)
        ref=Agent(checkpoint=checkpoint).requires_grad_(False).eval();model.eval();model.zero_grad(set_to_none=True)
        loss=trajectory_dpo(model,ref,(batch,torch.tensor([0,1],device='cuda'),None,1),head,.1)
        assert abs(float(loss.detach())-math.log(2))<1e-5
        loss.backward()
        head_gradient=float(model.action_head.grad.abs().max())
        payload_gradient=sum(float(p.grad.abs().sum())for n,p in model.named_parameters()if n.endswith('.0.B')and p.grad is not None)
        assert head_gradient<1e-5 and payload_gradient>0,(head_gradient,payload_gradient)
        assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters())
        # A discarded large test update crosses Q4 bins and verifies merged inference.
        optimizer=torch.optim.AdamW([p for p in model.parameters()if p.requires_grad],lr=.01)
        optimizer.step();assert model.frozen_digest()==original
        replica,info=model.packed(Path(tmp)/'check.mkqb');replica.to('cuda').eval();compact_head(replica,body_ids(tokenizer))
        texts=[x.request()for x in sessions[:4]]
        torch.backends.cuda.matmul.allow_tf32=False
        trained=generate(model,tokenizer,texts);merged=generate(replica,tokenizer,texts)
        assert [x['generated_token_ids']for x in trained]==[x['generated_token_ids']for x in merged]
    # Check matched history flags independently of correctness.
    pairs={}
    twins={};goal_labels={}
    for item in read(ROOT/'train-seeds.jsonl'):
        if item.get('same_code_inputs_facts_different_goal'):
            twins.setdefault(item['pair_id'],[]).append(item)
            key=(item['task_id'],item['prefill_revision'])
            goal_labels.setdefault(key,[]).append(item['intentionally_correct'])
            continue
        key=item['pair_id'];sig=tuple(item[k]for k in ['prefill_revision','pre_run_all','trace_before'])
        if key in pairs:assert pairs[key]==sig
        else:pairs[key]=sig
    assert all(sorted(labels)==[False,True]for labels in goal_labels.values())
    training_lookup={t['id']:t for t in read(ROOT/'train.jsonl')}
    for values in list(twins.values())[:24]:
        assert len(values)==2 and sorted(v['intentionally_correct']for v in values)==[False,True]
        left=make_session(training_lookup[values[0]['task_id']],values[0],vm)
        right=make_session(training_lookup[values[1]['task_id']],values[1],vm)
        assert left.body==right.body and left.runs==right.runs and left.case==right.case
        assert left.revision==right.revision and left.last_trace==right.last_trace
    documented=[t for t in read(ROOT/'isa-audit.jsonl')if t['kind']=='primitive'and t['catalog_risk']=='documented']
    compiler,tok=compiler_model()
    result={'isa':compiler_evaluate(compiler,tok,documented),'legacy':compiler_evaluate(compiler,tok,read(ROOT/'legacy-development.jsonl'))}
    assert result['isa']['passed']==648 and result['legacy']['passed']==69
    write(ROOT/'compiler-retention.json',result)
    names=[p.name for p in HERE.glob('ac_*.py')if p.name not in ['ac_remote.py','ac_export.py','ac_native.py','ac_verify.py','ac_collect.py','ac_report.py','ac_chat.py']]
    names+=['ab_eval.py','ab_protocol.py','aa_protocol.py','hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_vm.py','full_isa_bridge.cpp',
            'full_isa_math.py','full_isa_protocol.py','quantization.py','lowbit.py','native_quant.py','codec_common.py','hf_eval.py','emulator.py','ab_prepare.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,source/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()},
          'trainable_parameters':18560,'frozen_base_digest':original,'payload_preference_gradient':payload_gradient,
          'same_action_preference_head_gradient':head_gradient,'full_payload_preference_proven':True,
          'merged_Q4_inference_equal_after_test_update':True,'runtime_oracle_access_traps_passed':True,
          'matched_history_pairs':len(pairs),'bidirectional_goal_pairs':len(twins),
          'goal_label_balance_and_actual_fact_identity_checked':True,
          'compiler_ISA':648,'compiler_legacy':69,'test_update_discarded':True})
    print(json.dumps({'preflight':'passed','trainable_parameters':18560,'payload_gradient':payload_gradient,'compiler':[648,69]}),flush=True)


if __name__=='__main__':main()
