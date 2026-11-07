import json
import shutil
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from he_common import ROOT,INITIAL,INITIAL_PACKET,HERE,ARMS,read,sha,write,allowed
from he_runtime_check import main as runtime_check
from ha_protocol import constants,encode,write_call
from codec_train import compact_loss
from tasks import BUILD


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    runtime_check();torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.8)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    texts=[write_call(encode(t['reference_code'],t.get('constants')or constants(t['task']),'asm'))for t in read(ROOT/'sft-light.jsonl')]
    texts += [t['pair']['asm']['answer']for t in read(ROOT/'tool-lessons.jsonl')]
    for at in range(0,len(texts),512):
        assert {i for ids in tokenizer(texts[at:at+512],add_special_tokens=False)['input_ids']for i in ids}<=set(allowed())
    from he_train import Course,configure
    from native_quant import attach
    configure();a=Course(tokenizer);b=Course(tokenizer)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4');head=torch.tensor(allowed(),device='cuda');checks=[]
    for step in [1,2]:
        for arm,course in [('safe',a),('active',b)]:
            ids,mask,labels,lm=course.batch(arm,step,'cuda');model.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
            assert torch.isfinite(loss);loss.backward();assert all(p.grad is None or torch.isfinite(p.grad).all()for p in model.parameters())
            checks.append({'arm':arm,'loss':float(loss.detach()),'rows':len(ids),'max_tokens':ids.shape[1]})
    assert a.digest==b.digest and a.counts==b.counts
    names=['he_common.py','he_data.py','he_x_data.py','he_compact_data.py','he_tools.py','he_runtime.py','he_runtime_check.py','he_train.py','he_eval.py','he_prepare_run.py',
           'ha_train.py','ha_eval.py','ha_protocol.py','ha_runtime.py','ha_tools.py','full_isa_vm.py','full_isa_bridge.cpp','core_bridge.cpp',
           'full_isa_math.py','full_isa_protocol.py','codec_train.py','codec_common.py','codec_eval.py','native_quant.py','lowbit.py','quantization.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,source/n)
    files={**frozen['files'],**{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()}}
    write(ROOT/'prepared.json',{'files':files,'source_hashes':{n:sha(HERE/n)for n in names},
      'initial_master_sha256':frozen['initial_master_sha256'],'initial_packet_sha256':frozen['initial_packet_sha256'],
      'language_streams':{n:sha(BUILD/'native-mixed-v1/language'/n)for n in ['train.u16','validation.u16']},
      'preflight':checks,'same_course_digest':a.digest,'runtime_gate_has_no_reference_access':True,'fresh_used_for_selection':False})


if __name__=='__main__':main()
