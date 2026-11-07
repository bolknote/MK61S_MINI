"""Freeze paired examples, actual errors, repair seeds and acceptance floors."""
import collections
import json
import random
import shutil

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from ha_common import ROOT,INITIAL,INITIAL_PACKET,HERE,read,sha,write,allowed,compact_head
from ha_protocol import constants,encode,assemble,write_call
from ha_tools import seed,lessons
from ha_eval import development,brief
from full_isa_eval import generate as old_generate
from full_isa_common import task_prompt as old_prompt,allowed as old_allowed
from full_isa_protocol import decode
from full_isa_prepare import make_task
from full_isa_vm import FullVM,check_task
from lowbit import load
from tasks import BUILD,save_jsonl
from codec_train import compact_loss


def main():
    if(ROOT/'prepared.json').exists():return
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for filename,digest in frozen['files'].items():assert sha(ROOT/filename)==digest
    assert sha(INITIAL/'model.safetensors')==frozen['initial_master_sha256']and sha(INITIAL_PACKET)==frozen['initial_packet_sha256']
    vm=FullVM();rng=random.Random(6119210)
    validation=read(ROOT/'validation.jsonl');groups=collections.defaultdict(list)
    for t in validation:groups[t['group']].append(t)
    panel=[]
    for group,values in groups.items():
        rng.shuffle(values);panel+=values[:64 if group=='composition'else 40 if group in ['literal_copy','literal_function']else 24 if group=='register_source'else 12]
    save_jsonl(ROOT/'development.jsonl',panel)
    # The legacy suite is an observed regression, not a fresh exam.
    old=read(BUILD/'tasks/test-extended-v2.jsonl');legacy=[]
    for t in old:
        cases=t['public_tests']+t['hidden_tests'];inputs=[c['registers']for c in cases]
        task=make_task(vm,t['reference_code'],t['task'],t['id'],'legacy_observed','observed','RAD',inputs,kind='legacy',check_names=['X'])
        for case,expected in zip(task['public_tests']+task['hidden_tests'],cases):
            actual=float(case['segments'][0]['expected']['numeric']['X']);target=float(expected['expected_X'])
            assert abs(actual-target)<=max(2e-6,abs(target)*2e-6)
        legacy.append(task)
    save_jsonl(ROOT/'legacy-development.jsonl',legacy)
    # All repair starts are fixed before any new model optimization.
    for split in ['validation','fresh']:
        tasks=read(ROOT/(split+'.jsonl'));ids=set(json.loads((ROOT/(split+'-tool-ids.json')).read_text()))
        chosen=[t for t in tasks if t['id']in ids];items=[seed(t,correct=i%4==0,vm=vm,salt=6119210)for i,t in enumerate(chosen)]
        save_jsonl(ROOT/(split+'-tool-seeds.jsonl'),items)
    train=read(ROOT/'train.jsonl');buckets=collections.defaultdict(list)
    for t in train:buckets[t['group']].append(t)
    chosen=[]
    for values in buckets.values():rng.shuffle(values);chosen+=values[:56]
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.8);torch.backends.cuda.matmul.allow_tf32=False
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    load(model,INITIAL_PACKET);model.to('cuda').eval();compact_head(model,old_allowed());errors={}
    probe=chosen[:256]
    for at in range(0,len(probe),16):
        batch=probe[at:at+16];replies=old_generate(model,tokenizer,[old_prompt(t)for t in batch])
        for task,row in zip(batch,replies):
            try:code=decode(row['reply']);ok=check_task(vm,code,task,public=True)['pass']
            except (ValueError,RuntimeError,ArithmeticError):code=[0x54,0x50];ok=False
            if not ok:errors[task['id']]=code
    lesson_rows=[];origins=collections.Counter()
    for i,task in enumerate(chosen):
        item=seed(task,correct=i%5==0 and task['id']not in errors,vm=vm,salt=6119213,wrong=errors.get(task['id']))
        lesson_rows+=lessons(task,item,vm);origins[item['origin']['source']]+=1
    save_jsonl(ROOT/'tool-lessons.jsonl',lesson_rows)
    # Compact head must contain every supervised token in both formats.
    required=set(allowed());texts=[]
    for task in read(ROOT/'sft-light.jsonl'):
        pool=task.get('constants')or constants(task['task'])
        for arm in ['direct','asm']:texts.append(write_call(encode(task['reference_code'],pool,arm)))
    texts += [value['answer']for row in lesson_rows for value in row['pair'].values()]
    for at in range(0,len(texts),512):
        actual={t for ids in tokenizer(texts[at:at+512],add_special_tokens=False)['input_ids']for t in ids}
        assert actual<=required,actual-required
    compact_head(model,allowed());baselines={}
    for arm in ['direct','asm']:
        baseline=development(model,tokenizer,arm);baselines[arm]=baseline
        write(ROOT/('baseline-development-'+arm+'.json'),{'metrics':baseline,'summary':brief(baseline)})
    floors={'legacy':max(x['legacy']['rate']for x in baselines.values())-.03,
      'scientific':max(x['isa']['by_kind']['numeric_synthesis']['rate']for x in baselines.values())-.03,
      'programming':max(x['isa']['by_kind']['programming']['rate']for x in baselines.values())-.03,
      'chosen_before_optimizer_updates':True,'same_floors_for_both_arms':True}
    write(ROOT/'retention-floors.json',floors);del model,train,chosen
    from ha_train import Course
    from native_quant import attach
    a=Course(tokenizer);b=Course(tokenizer)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    head=torch.tensor(allowed(),device='cuda');checks=[]
    for step in [1,501]:
        for arm,course in [('direct',a),('asm',b)]:
            ids,mask,labels,lm=course.batch(arm,step,'cuda');model.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
            assert torch.isfinite(loss);loss.backward();checks.append({'arm':arm,'step':step,'loss':float(loss.detach()),'rows':len(ids),'max_tokens':ids.shape[1]})
    assert a.digest==b.digest and a.counts==b.counts
    source_names=['ha_common.py','ha_protocol.py','ha_runtime.py','ha_data.py','ha_tools.py','ha_eval.py','ha_train.py','ha_prepare_run.py',
      'full_isa_vm.py','full_isa_bridge.cpp','core_bridge.cpp','full_isa_math.py','full_isa_protocol.py','codec_train.py','codec_common.py','codec_eval.py',
      'native_quant.py','lowbit.py','quantization.py']
    snapshot=ROOT/'training-source';snapshot.mkdir(exist_ok=True)
    for name in source_names:shutil.copyfile(HERE/name,snapshot/name)
    files={**frozen['files']}
    for name in ['development.jsonl','legacy-development.jsonl','tool-lessons.jsonl','retention-floors.json','validation-tool-seeds.jsonl','fresh-tool-seeds.jsonl']:files[name]=sha(ROOT/name)
    files.update({str(p.relative_to(ROOT)):sha(p)for p in snapshot.iterdir()})
    prepared={'before_optimizer_updates':True,'files':files,'source_hashes':{name:sha(HERE/name)for name in source_names},
      'initial_master_sha256':frozen['initial_master_sha256'],'initial_packet_sha256':frozen['initial_packet_sha256'],
      'language_streams':{name:sha(BUILD/'native-mixed-v1/language'/name)for name in ['train.u16','validation.u16']},
      'same_course_digest':a.digest,'preflight':checks,'tool_episodes':sum(origins.values()),'tool_lessons':len(lesson_rows),
      'tool_origins':dict(origins),'actual_pretrained_errors':len(errors),'fresh_used_for_selection':False,'feedback_has_expected_output':False}
    write(ROOT/'prepared.json',prepared)
    print(json.dumps({k:v for k,v in prepared.items()if k not in ['files','source_hashes','language_streams','preflight']}),flush=True)


if __name__=='__main__':main()
