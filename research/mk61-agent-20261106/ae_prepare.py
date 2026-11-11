"""Pre-SGD semantic-label, embedding-protection and merged-Q4 equivalence checks."""
import json
import shutil
import tempfile
from pathlib import Path
import torch
from ae_common import ROOT,HERE,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,read,write,sha,body_ids,output_ids,compact_head
from ae_model import Agent
from ae_course import batch_pad,loss
from ae_eval import generate
from ae_teacher import correct,make_session
from full_isa_vm import FullVM
from ac_eval import generate as old_generate


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for name,digest in frozen['files'].items():assert sha(ROOT/name)==digest,name
    assert sha(INITIAL_PACKET)==frozen['initial_tool_packet_sha256']and sha(COMPILER_PACKET)==frozen['compiler_packet_sha256']
    torch.set_num_threads(4);torch.manual_seed(712501);torch.cuda.set_per_process_memory_fraction(.8);torch.backends.cuda.matmul.allow_tf32=False
    lessons=read(ROOT/'lessons.jsonl');assert all(r['correctness']==1 and r['eligible_for_DONE']for r in lessons if r['action']=='done')
    assert any(r['level']>=2 and r['action']=='write'for r in lessons)
    tasks={t['id']:t for t in read(ROOT/'train.jsonl')};vm=FullVM();pairs={};checked=0
    for seed in read(ROOT/'train-seeds.jsonl')[:64]:
        s=make_session(tasks[seed['task_id']],seed,vm);assert correct(vm,tasks[seed['task_id']],s.body,s.pool)==seed['intentionally_correct']
        signature=tuple(str(seed[k])for k in ['pool','prefill_revision','pre_run_all','trace_before','critic_warning','error_probe'])
        if seed['pair_id']in pairs:assert pairs[seed['pair_id']]==signature
        else:pairs[seed['pair_id']]=signature
        assert not({'hidden_tests','reference_code'}&set(s.task));assert all('expected'not in x for c in s.task['public_tests']for x in c['segments']);checked+=1
    dev={t['id']:t for t in read(ROOT/'development.jsonl')};samples=read(ROOT/'development-seeds.jsonl')[:4]
    prompts=[make_session(dev[i['task_id']],i,vm).request()for i in samples];records={}
    for arm in ['lora16','full']:
        model=Agent(arm);before=model.input_digest();packed,_=model.packed(ROOT/f'preflight-{arm}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(model.tokenizer))
        initial=generate(model,model.tokenizer,prompts);plain=generate(packed,model.tokenizer,prompts);original=old_generate(packed,model.tokenizer,prompts)
        assert [r['generated_token_ids']for r in initial]==[r['generated_token_ids']for r in plain]==[r['generated_token_ids']for r in original]
        rows=[next(r for r in lessons if r['correctness']==truth and r['action']==action)for truth,action in [(0,'write'),(1,'done'),(0,'run'),(1,'run')]]
        batch=batch_pad(model.tokenizer,rows,'cuda');optimizer=torch.optim.AdamW([p for p in model.parameters()if p.requires_grad],lr=.005)
        value,parts=loss(model,batch,torch.tensor(body_ids(model.tokenizer),device='cuda'));value.backward()
        assert model.correct_head.grad is not None and model.correct_head.grad.abs().sum()>0
        assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters());optimizer.step();assert model.input_digest()==before
        replica,_=model.packed(ROOT/f'preflight-{arm}-updated.mkqb');replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
        updated=generate(model,model.tokenizer,prompts);merged=generate(replica,model.tokenizer,prompts)
        assert [r['generated_token_ids']for r in updated]==[r['generated_token_ids']for r in merged]
        error=max(abs(a['correctness_margin']-b['correctness_margin'])for a,b in zip(updated,merged));assert error<1e-4,error
        records[arm]={'trainable_parameters':model.trainable_count(),'input_embedding_digest':before,'Q4_merge_streams_equal_after_test_update':True,'margin_max_error':error}
        del model,packed,replica,optimizer,batch;torch.cuda.empty_cache()
    excluded={'ae_remote.py','ae_collect.py','ae_export.py','ae_native.py','ae_verify.py','ae_report.py','ae_chat.py','ae_demos.py'}
    names=[p.name for p in HERE.glob('ae_*.py')if p.name not in excluded]
    names+=['ac_protocol.py','ac_runtime.py','ac_model.py','ac_course.py','ac_eval.py','ab_eval.py','hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_vm.py','full_isa_math.py','native_quant.py','quantization.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for name in names:shutil.copyfile(HERE/name,source/name)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()},
       'arms':records,'matched_cases_checked':checked,'all_DONE_labels_true_and_eligible':True,'test_optimizer_updates_discarded':True,
       'no_test_update_checkpoint_reused':True,'runtime_has_no_expected_hidden_reference':True})
    print(json.dumps({'preflight':'passed','arms':records}),flush=True)


if __name__=='__main__':main()
