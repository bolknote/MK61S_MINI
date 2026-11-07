"""Freeze balanced panels, actual student errors and the concrete training data."""
import collections
import hashlib
import json
import random
import re

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from full_isa_common import ROOT,INITIAL,INITIAL_PACKET,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA,read,sha,write,allowed,compact_head,task_prompt,target
from full_isa_protocol import decode,linear_instructions
from full_isa_vm import FullVM,check_task
from full_isa_eval import generate,failed_feedback,development,brief
from lowbit import load
from tasks import BUILD,save_jsonl

LIGHT_KEYS=['id','task','angle','reference_code','group','kind','opcode','catalog_risk','target_opcodes','source']


def light_rows(path):
    with path.open()as stream:
        for line in stream:
            row=json.loads(line);yield {k:row[k]for k in LIGHT_KEYS if k in row}


def main():
    if(ROOT/'prepared.json').exists():print('Full ISA training inputs already frozen');return
    base=json.loads((ROOT/'data-frozen.json').read_text());run=json.loads((ROOT/'run-policy-frozen.json').read_text())
    assert all(sha(ROOT/k)==v for k,v in base['files'].items())
    assert all(sha(ROOT/k)==v for k,v in run['files'].items())
    assert all(sha(ROOT/'core-source'/k)==v for k,v in run['private_core_files'].items())
    assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA and sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    assert base['reference_all_256_opcodes_executed']
    # Keep full fixtures on disk; SGD only loads text/code metadata into memory.
    light=list(light_rows(ROOT/'train.jsonl'))+list(light_rows(ROOT/'historical-fragments.jsonl'))+list(light_rows(ROOT/'teacher/train.jsonl'))
    save_jsonl(ROOT/'sft-light.jsonl',light)
    old=BUILD/'semantic-3m-v1'
    if not(old/'train.jsonl').exists():old=old/'server-results'
    legacy=[]
    for row in read(old/'train.jsonl'):
        legacy.append({'id':'legacy:'+row['id'],'task':row['task'],'angle':'RAD','reference_code':row['reference_code'],
          'kind':'legacy','group':'legacy_replay','source':'previous_verified_training'})
    save_jsonl(ROOT/'legacy-light.jsonl',legacy)
    validation=read(ROOT/'validation.jsonl');panel=[]
    for row in validation:
        if row['kind']=='primitive':
            if row['angle']==['RAD','DEG','GRAD'][row['opcode']%3]or row['opcode']in range(0x19,0x1F):panel.append(row)
    numerical=[r for r in validation if r['kind']=='numeric_synthesis'];byop=collections.defaultdict(list)
    for row in numerical:byop[tuple(row['target_opcodes'])].append(row)
    for values in byop.values():panel+=values[:3]
    panel += [r for r in validation if r['kind']in ['programming','interactive_game']]
    save_jsonl(ROOT/'development.jsonl',panel)
    # Tool subset is fixed by IDs before any new audit evaluation.
    audit=read(ROOT/'audit.jsonl');groups=collections.defaultdict(list)
    for row in audit:groups[row['group']].append(row)
    selected=[];rng=random.Random(6117060)
    for values in groups.values():
        rng.shuffle(values);selected += values[:2 if values[0]['kind']=='primitive'else 12]
    write(ROOT/'tool-probe-ids.json',[r['id']for r in selected])
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.8)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    allowed_set=set(allowed());target_texts=[target(r['reference_code'])for r in light+legacy]+['<trace/>','<done/>']
    for at in range(0,len(target_texts),1024):
        encoded=tokenizer(target_texts[at:at+1024],add_special_tokens=False)['input_ids']
        missing={token for row in encoded for token in row}-allowed_set
        assert not missing,('Output head omits supervised tokens',missing)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False);load(model,INITIAL_PACKET);model.to('cuda').eval();compact_head(model,allowed())
    vm=FullVM();canonical=read(ROOT/'train.jsonl');probe=[]
    for row in canonical:
        if row['kind']=='primitive'and row['angle']=='RAD'and':wording0'in row['id']:probe.append(row)
    for kind,n in [('numeric_synthesis',64),('programming',40),('interactive_game',8)]:
        choices=[r for r in canonical if r['kind']==kind];rng.shuffle(choices);probe+=choices[:n]
    errors=[];observed=[]
    for at in range(0,len(probe),16):
        batch=probe[at:at+16];replies=generate(model,tokenizer,[task_prompt(t)for t in batch])
        for row,reply in zip(batch,replies):
            try:code=decode(reply['reply']);result=check_task(vm,code,row,public=True)
            except (ValueError,RuntimeError,ArithmeticError):code=None;result={'pass':False,'details':[]}
            observed.append({'id':row['id'],'public_pass':result['pass'],'reply':reply['reply']})
            if not result['pass']:
                observation=failed_feedback(row,result)if result['details']else'FAIL: некорректный формат программы HEX.'
                errors.append({'id':'actual:'+row['id'],'task':row['task'],'angle':row['angle'],'current_code':code,
                  'observation':observation,'reference_code':row['reference_code'],'kind':'actual_error','group':row['group']})
        print(json.dumps({'initial_training_probe':min(at+16,len(probe)),'total':len(probe),'errors':len(errors)}),flush=True)
    # Real-core synthetic corrections broaden tools beyond the initial model's errors.
    rng.shuffle(canonical);synthetic=[]
    for row in canonical:
        if len(synthetic)>=384:break
        try:starts=[s['pc']for s in linear_instructions(row['reference_code'])if s['opcode']!=0x50]
        except ValueError:continue
        for attempt in range(5):
            wrong=list(row['reference_code']);at=rng.choice(starts);original=wrong[at]
            if 0x60<=original<=0x6E:wrong[at]=0x60+(original-0x60+1)%15
            elif original in [0x1C,0x1D,0x1E]:wrong[at]={0x1C:0x1D,0x1D:0x1E,0x1E:0x1C}[original]
            else:wrong[at]=rng.choice([0x10,0x11,0x12,0x13,0x22,0x31,0x54])
            if wrong==row['reference_code']:continue
            checked=check_task(vm,wrong,row,public=True)
            if not checked['pass']:break
        else:continue
        actual,_=vm.execute(wrong,row['public_tests'][0]['segments'][0]['inputs'],angle=row['angle'],max_commands=128,max_frames=1024)
        trace='TRACE '+ '; '.join(f'{s["pc"]:02}:{s["opcode"]:02X}'for s in actual['trace'][:10])+'; X='+actual['raw']['X']
        synthetic.append({'id':'synthetic:'+row['id'],'task':row['task'],'angle':row['angle'],'current_code':wrong,
          'reference_code':row['reference_code'],'observation':failed_feedback(row,checked),'trace':trace,'group':row['group'],'kind':'synthetic_error'})
    save_jsonl(ROOT/'repair-examples.jsonl',errors+synthetic);save_jsonl(ROOT/'initial-training-probe.jsonl',observed)
    # Baseline on validation only. The new audit remains unopened for scoring.
    baseline=development(model,tokenizer);write(ROOT/'baseline-development.json',{'metrics':baseline,'summary':brief(baseline),'packet_sha256':INITIAL_PACKET_SHA})
    del model,canonical,probe,validation,audit
    from full_isa_train import Course
    from codec_train import compact_loss
    from native_quant import attach
    course_a=Course(tokenizer);course_b=Course(tokenizer)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    head=torch.tensor(allowed(),device='cuda');checks=[]
    for step,context in enumerate([512,1024,2048],1):
        for arm,course in [('full',course_a),('protected',course_b)]:
            ids,mask,labels,lm=course.batch(context,step,'cuda');model.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
            assert torch.isfinite(loss);loss.backward()
            checks.append({'arm':arm,'context':context,'loss':float(loss.detach()),'rows':len(ids),'max_tokens':ids.shape[1]})
            del ids,mask,labels,lm,loss
        assert course_a.digest==course_b.digest and course_a.counts==course_b.counts
    write(ROOT/'preflight.json',{'checks':checks,'sample_plans_match':True,'optimizer_updates':0})
    files={name:sha(ROOT/name)for name in ['sft-light.jsonl','legacy-light.jsonl','repair-examples.jsonl','development.jsonl',
      'tool-probe-ids.json','baseline-development.json','preflight.json','policy.json','catalog.json','output-token-ids.json','data-frozen.json','run-policy-frozen.json']}
    manifest={'before_new_optimizer_updates':True,'initial_master_sha256':INITIAL_MASTER_SHA,'initial_packet_sha256':INITIAL_PACKET_SHA,
      'files':files,'canonical_and_teacher_rows':len(light),'legacy_rows':len(legacy),'actual_initial_errors':len(errors),'synthetic_errors':len(synthetic),
      'development_rows':len(panel),'tool_probe_tasks':len(selected),'teacher_manifest_sha256':sha(ROOT/'teacher/manifest.json'),
      'full_reference_opcode_coverage':1.,'audit_used_for_selection':False,
      'initial_write_tag_is_fixed_protocol_framing':False,'language_streams':{n:sha(BUILD/'native-mixed-v1/language'/n)for n in ['train.u16','validation.u16']}}
    write(ROOT/'prepared.json',manifest);print(json.dumps({k:v for k,v in manifest.items()if k not in ['files','language_streams']}),flush=True)


if __name__=='__main__':main()
