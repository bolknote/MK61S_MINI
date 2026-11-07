"""Freeze repair observations, source versions and finite-gradient preflight."""
import json
from pathlib import Path
import shutil

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from natural_common import ROOT,INITIAL,INITIAL_PACKET,read,sha,write,allowed,compact_head,task_prompt,target
from full_isa_eval import generate,failed_feedback
from full_isa_protocol import decode
from full_isa_vm import FullVM,check_task
from lowbit import load
from tasks import BUILD,save_jsonl
from codec_train import compact_loss


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for filename,digest in frozen['files'].items():assert sha(ROOT/filename)==digest
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']
    assert sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.8)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    targets=[target(x['reference_code'])for x in read(ROOT/'sft-light.jsonl')]
    for at in range(0,len(targets),512):
        actual={t for row in tokenizer(targets[at:at+512],add_special_tokens=False)['input_ids']for t in row}
        assert actual<=set(allowed())
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    load(model,INITIAL_PACKET);model.to('cuda').eval();compact_head(model,allowed());vm=FullVM()
    tasks=read(ROOT/'train-language.jsonl');repairs=read(ROOT/'repair-examples.jsonl');errors=[]
    chosen=[]
    for group in sorted({x['group']for x in tasks}):chosen += [t for t in tasks if t['group']==group][:32]
    for at in range(0,len(chosen),16):
        batch=chosen[at:at+16];outputs=generate(model,tokenizer,[task_prompt(t)for t in batch])
        for task,reply in zip(batch,outputs):
            try:code=decode(reply['reply']);checked=check_task(vm,code,task,public=True)
            except (ValueError,RuntimeError,ArithmeticError):code=None;checked={'pass':False,'details':[]}
            if not checked['pass']:
                feedback=failed_feedback(task,checked)if checked['details']else'FAIL: требуется полная программа HEX.'
                errors.append({'id':'fresh-error:'+task['id'],'task':task['task'],'angle':task['angle'],
                  'reference_code':task['reference_code'],'current_code':code,'observation':feedback,'group':task['group']})
    save_jsonl(ROOT/'fresh-repair-examples.jsonl',repairs+errors)
    from natural_eval import development,brief
    baseline=development(model,tokenizer);write(ROOT/'baseline-development.json',{'summary':brief(baseline),'metrics':baseline})
    del model,tasks
    import full_isa_train as training
    from natural_train import Course
    from native_quant import attach
    training.ROOT=ROOT
    ca=Course(tokenizer);cb=Course(tokenizer)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    head=torch.tensor(allowed(),device='cuda');checks=[]
    for step,context in enumerate([512,1024,2048],1):
        for arm,course in [('full',ca),('protected',cb)]:
            ids,mask,labels,lm=course.batch(context,step,'cuda');model.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
            assert torch.isfinite(loss);loss.backward()
            checks.append({'arm':arm,'context':context,'loss':float(loss.detach()),'rows':len(ids)})
    assert ca.digest==cb.digest and ca.counts==cb.counts
    source_names=['natural_common.py','natural_data.py','natural_train.py','natural_eval.py','natural_prepare_run.py']
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for name in source_names:shutil.copyfile(Path(__file__).parent/name,source/name)
    files={**frozen['files'],'fresh-repair-examples.jsonl':sha(ROOT/'fresh-repair-examples.jsonl')}
    files.update({str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()})
    prepared={'before_new_optimizer_updates':True,'files':files,'initial_master_sha256':frozen['initial_master_sha256'],
      'initial_packet_sha256':frozen['initial_packet_sha256'],'natural_source_hashes':{p.name:sha(p)for p in source.iterdir()},
      'language_streams':{name:sha(BUILD/'native-mixed-v1/language'/name)for name in ['train.u16','validation.u16']},
      'preflight':checks,'same_course_digest':ca.digest,'actual_initial_errors':len(errors),
      'new_training_rows':frozen['new_training_rows'],'fresh_language_rows':frozen['fresh_language_rows'],
      'validation_language_rows':frozen['validation_language_rows'],'fresh_language_used_for_selection':False}
    write(ROOT/'prepared.json',prepared)
    print(json.dumps({k:v for k,v in prepared.items()if k not in ['files','natural_source_hashes','language_streams','preflight']}),flush=True)


if __name__=='__main__':main()
