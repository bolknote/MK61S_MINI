"""Freeze new training/validation corpus and actual initial-student error replay."""
import collections
import hashlib
import json
import random
import re

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from semantic_common import ROOT,INITIAL,INITIAL_PACKET,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA,read,sha,write_json,compact_head,allowed_ids,protocol
from codec_eval import generate_batch
from course_common import program_prompt,answer
from course_eval import grading_tasks
from emulator import Emulator
from harness import extract_code,check_program,feedback
from lowbit import load
from tasks import BUILD,save_jsonl


def sample(rows,count,seed):
    rows=list(rows);random.Random(seed).shuffle(rows);return rows[:count]


def main():
    if(ROOT/'prepared.json').exists():print('Frozen semantic preparation complete');return
    assert sha(INITIAL/'model.safetensors')==INITIAL_MASTER_SHA and sha(INITIAL_PACKET)==INITIAL_PACKET_SHA
    frozen=json.loads((ROOT/'audit-frozen.json').read_text());assert all(sha(ROOT/k)==v['sha256']for k,v in frozen['files'].items())
    train=read(ROOT/'teacher/train.jsonl');validation=read(ROOT/'teacher/validation.jsonl')
    assert len(train)>=3000
    assert not {t['language_family']for t in train}&{t['language_family']for t in validation}
    assert not {t['source_id']for t in train}&{t['source_id']for t in validation}
    old=BUILD/'codec-qat-v1';legacy=read(old/'train.jsonl')
    for row in legacy:row['source']='legacy';row['language_family']='legacy:'+row['id']
    old_sample=[]
    for level,count in [(1,4000),(2,2000),(3,2000)]:old_sample+=sample([t for t in legacy if t['level']==level],count,6116012+level)
    save_jsonl(ROOT/'train.jsonl',train+old_sample)
    for level in [1,2,3]:
        save_jsonl(ROOT/f'validation-new{level}.jsonl',sample([t for t in validation if t['level']==level],16 if level==1 else 40,6116015+level))
        observed=read(old/f'development{level}.jsonl')+read(old/f'fresh{level}.jsonl')
        save_jsonl(ROOT/f'validation-observed{level}.jsonl',sample(observed,24,6116020+level))
    save_jsonl(ROOT/'formal-development.jsonl',read(old/'formal-development.jsonl'))
    replay=sample(read(old/'replay.jsonl'),4000,6116024)
    # Error collection never opens audit.jsonl and never uses validation cases.
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.8)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False);load(model,INITIAL_PACKET)
    model.to('cuda').eval();compact_head(model,allowed_ids('hex'));em=Emulator();rows=[];failures=[]
    selected=[]
    for level,n in [(1,64),(2,224),(3,224)]:selected+=sample([r for r in train if r['level']==level],n,6116025+level)
    selected=grading_tasks(selected)
    for at in range(0,len(selected),8):
        batch=selected[at:at+8]
        replies=generate_batch(model,tokenizer,[program_prompt(t)for t in batch],protocol('hex'),max_new=160)
        for task,row in zip(batch,replies):
            code=extract_code(row['reply']);checked=check_program(em,code,task['public_tests'])if code and'<run/>'in row['reply']else{'pass':False}
            rows.append({'id':task['id'],'public_pass':checked['pass'],'reply':row['reply']})
            if checked['pass']:continue
            observation=feedback(checked)if code and'details'in checked else 'FAIL: программа не прошла открытые примеры.'
            if code:prompt=program_prompt({**task,'initial_code':code},observation=observation)
            else:prompt=program_prompt(task,observation='FAIL: неверный формат вызова. Требуются <calc>, <write>HEX</write> и <run/>.')
            failures.append({'id':'initial-error:'+task['id'],'prompt':prompt,'answer':answer(task),'source':'actual_initial_student_train_error','training_task_id':task['id']})
        if at%64==0:print(json.dumps({'student_training_error_probe':min(at+8,len(selected)),'total':len(selected),'errors':len(failures)}),flush=True)
    save_jsonl(ROOT/'initial-student-train-probe.jsonl',rows);save_jsonl(ROOT/'actual-error-replay.jsonl',failures)
    save_jsonl(ROOT/'replay.jsonl',replay);del model
    resources={'effective_batch':128,'micro_by_context':{'512':128,'1024':128,'2048':128},'memory_fraction_each':.8,
      'workers_each_gpu':1,'assignment':{'direct':0,'auxiliary':1},'auxiliary_examples_each_update':32,'both_full_cards_authorized':True}
    write_json(ROOT/'resources.json',resources)
    # Exercise both real loss paths at all configured lengths before starting
    # either optimizer. Sampling must agree even when the auxiliary targets
    # need the full Russian readout and are longer than compact parses.
    from semantic_train import Course
    from codec_train import compact_loss
    from native_quant import attach
    courses={arm:Course(tokenizer)for arm in ['direct','auxiliary']}
    probe_model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False).to('cuda');attach(probe_model,'q4')
    probes=[];output=torch.tensor(allowed_ids('hex'),device='cuda')
    for step,context in enumerate([512,1024,2048],1):
        for arm in ['direct','auxiliary']:
            ids,mask,labels,lm=courses[arm].batch(arm,context,step,'cuda');probe_model.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(probe_model,ids,mask,labels,lm,output)
            assert torch.isfinite(loss);loss.backward()
            gradient=probe_model.get_input_embeddings().parametrizations.weight.original.grad
            assert gradient is not None and torch.isfinite(gradient).all()and gradient.norm()>0
            probes.append({'arm':arm,'context':context,'rows':len(ids),'tokens_max':ids.shape[1],'loss':float(loss.detach()),'full_russian_head_rows':int(lm.sum())})
            del loss,ids,mask,labels,lm
        assert courses['direct'].plan_digest==courses['auxiliary'].plan_digest
        assert courses['direct'].counts==courses['auxiliary'].counts
    write_json(ROOT/'preflight-loss.json',{'finite_loss_and_gradients_both_arms':True,'same_sample_plan_all_contexts':True,'optimizer_updates':0,'probes':probes})
    del probe_model,courses
    files={p.name:{'sha256':sha(p),'rows':len(read(p))if p.suffix=='.jsonl'else None}for p in ROOT.iterdir()if p.is_file()and p.suffix in ['.json','.jsonl']and p.name not in ['prepared.json','status.json','data-launch.json','start-launch.json']}
    # Do not include mutable orchestration/runtime markers in training inputs.
    files={k:v for k,v in files.items()if k in ['policy.json','resources.json','audit-frozen.json','audit.jsonl','train.jsonl','replay.jsonl','actual-error-replay.jsonl','formal-development.jsonl']or k.startswith('validation-')}
    manifest={'before_any_new_optimizer_updates':True,'initial_master_sha256':INITIAL_MASTER_SHA,'initial_packet_sha256':INITIAL_PACKET_SHA,
      'new_teacher_training_conditions':len(train),'legacy_replay_conditions':len(old_sample),'initial_student_train_probe':len(rows),
      'actual_training_errors':len(failures),'new_audit_opened_for_rollouts':False,'files':files,
      'preflight_loss_sha256':sha(ROOT/'preflight-loss.json'),
      'teacher_manifest_sha256':sha(ROOT/'teacher/manifest.json'),'language_streams':{k:sha(BUILD/'native-mixed-v1/language'/k)for k in ['train.u16','validation.u16']}}
    write_json(ROOT/'prepared.json',manifest);print(json.dumps({k:v for k,v in manifest.items()if k!='files'}),flush=True)


if __name__=='__main__':main()
