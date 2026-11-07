"""Check runtime information boundaries and exact losses before any SGD."""
import copy
import json
import math
import shutil
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from aa_common import ROOT, INITIAL, INITIAL_PACKET, HERE, ACTION_ID, ACTION_IDS, read,write,sha,body_ids,output_ids
from aa_protocol import target_ids,decode,Grammar
from aa_course import Course,separate_loss,preference_loss
from aa_runtime import Session
from native_quant import attach
from full_isa_vm import FullVM


class PublicOnly(dict):
    def __getitem__(self,key):
        if key in ['reference_code','hidden_tests','expression','expected']:raise AssertionError('Runtime oracle access: '+key)
        return super().__getitem__(key)
    def get(self,key,default=None):
        if key in ['reference_code','hidden_tests','expression','expected']:raise AssertionError('Runtime oracle access: '+key)
        return super().get(key,default)


def main():
    if(ROOT/'prepared.json').exists():return
    data=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in data['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==data['initial_master_sha256']
    assert sha(INITIAL_PACKET)==data['initial_packet_sha256']
    torch.set_num_threads(4);torch.manual_seed(712412);torch.cuda.set_per_process_memory_fraction(.8)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    g=Grammar(tokenizer,0);roundtrips=0
    for action in ACTION_ID:
        bodies=[[]]if action in ['done','trace','unsure']else [[i]for i in range(256)]if action=='run'else [[1,28,29,0,i]for i in range(256)]if action=='diag'else [[0,0,i]for i in range(256)]if action=='patch'else [[i]for i in range(256)]
        for body in bodies:
            tokens=target_ids(tokenizer,action,body);assert decode(tokenizer,tokens)==(action,body)
            text=''
            for token in tokens[1:]:
                assert token in g.permitted(action,text),(action,text,token)
                if token!=tokenizer.eos_token_id:text+=g.pieces[token]
            roundtrips+=1
    vm=FullVM();t=copy.deepcopy(read(ROOT/'validation.jsonl')[0]);t=PublicOnly(t)
    t['public_tests']=[{'segments':[PublicOnly(s)for s in c['segments']]}for c in t['public_tests']]
    from ha_protocol import constants,encode
    raw=read(ROOT/'validation.jsonl')[0]['reference_code'];session=Session(t,'asm',body=encode(raw,constants(t['task']),'asm'),vm=vm,gate=False)
    for i in range(len(t['public_tests'])):session.run(i)
    session.request();session.apply_action('trace',[])
    session.apply_action('diag',[4,session.body[0],session.body[0],0,0]);session.request()
    assert session.apply_action('done',[])=='done'
    other=Session(t,'asm',body=session.body,vm=vm,gate=False)
    assert other.apply_action('unsure',[])=='unsure'and other.abstained and not other.finished
    course=Course(tokenizer,0);second=Course(tokenizer,0)
    batch=course.batch(1,'cuda');replica=second.batch(1,'cuda')
    assert all(torch.equal(x,y)for x,y in zip(batch,replica))and course.digest==second.digest
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True).to('cuda');attach(model,'q4')
    with torch.autocast('cuda',dtype=torch.bfloat16):loss,parts=separate_loss(model,batch,torch.tensor(body_ids(tokenizer),device='cuda'))
    assert torch.isfinite(loss);loss.backward();assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters())
    # Equal action loss is independent of answer token count by construction.
    model.eval();pref=course.preferences(4,'cuda')
    with torch.autocast('cuda',dtype=torch.bfloat16):dpo=preference_loss(model,model,*pref,.2)
    assert abs(float(dpo.detach())-math.log(2))<1e-5
    names=sorted(p.name for p in HERE.glob('aa_*.py')if p.name not in ['aa_remote.py','aa_verify.py','aa_report.py'])
    names+=['hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_vm.py','full_isa_bridge.cpp','full_isa_math.py','native_quant.py','quantization.py','lowbit.py']
    names+=['aa_native.hpp','aa_native_probe.cpp']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,source/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()},
          'protocol_roundtrips':roundtrips,'output_rows':len(output_ids(tokenizer)),'finite_separate_loss':float(loss.detach()),
          'loss_components':parts,'initial_DPO_equals_log2':True,'same_SFT_draws_verified':True,
          'runtime_oracle_access_traps_passed':True,'DIAG_is_only_a_hypothesis':True,'UNSURE_is_not_success':True})
    print(json.dumps({'preflight':'passed','roundtrips':roundtrips,'output_rows':len(output_ids(tokenizer)),'loss':parts}),flush=True)


if __name__=='__main__':main()
