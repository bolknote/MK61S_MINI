import collections
import copy
import json
import random
import re
import shutil
import time

from transformers import AutoTokenizer
from vc_common import ROOT,CODER,INITIAL,INITIAL_PACKET,read,sha,write
from vc_protocol import executed_prompt
from hf_tools import seed
from ha_protocol import constants,assemble
from full_isa_vm import FullVM,check_task
from tasks import save_jsonl


def build(tasks,part,vm,negatives):
    rows=[];seen=set();started=time.monotonic()
    for i,task in enumerate(tasks):
        candidates=[(task['reference_code'],True,'reference')]
        for j in range(negatives):
            item=seed(task,vm,6120900+i*7+j);candidates.append((item['initial_code'],False,'mutation'))
        # Reachable semantics, rather than identical source bytes, define correctness.
        if part=='train'and i%3==0:
            alt=[*task['reference_code'],0x54]
            if len(alt)<=105 and check_task(vm,alt,task)['pass']:candidates.append((alt,True,'valid_variant'))
        for code,label,origin in candidates:
            key=(task['id'],tuple(code))
            if key in seen:continue
            seen.add(key);assert bool(check_task(vm,code,task)['pass'])==label
            rows.append({'id':f'{part}:{i}:{len(rows)}','task_id':task['id'],'prompt':executed_prompt(task,code,vm),
                         'code':code,'label':int(label),'origin':origin,'split':part,'expected_values_in_prompt':False})
        if i%500==0:print(json.dumps({'split':part,'tasks':i,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    return rows


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();sets={}
    for part,name,n in [('train','train.jsonl',2),('validation','validation.jsonl',1),('fresh','fresh.jsonl',1)]:
        path=ROOT/(part+'.jsonl')
        if path.exists():sets[part]=read(path)
        else:
            sets[part]=build(read(CODER/name),part,vm,n);save_jsonl(path,sets[part])
    lookup={t['id']:t for t in read(CODER/'train.jsonl')}
    extra=[]
    for i,row in enumerate(read(CODER/'dagger-lessons.jsonl')):
        body=[];inside=False
        for line in row['prompt'].splitlines():
            if line.startswith('Текущий HEX'):inside=True;continue
            if inside:
                match=re.fullmatch(r'[0-9A-F]{4}: (.*)',line)
                if not match:break
                body += [int(x,16)for x in match.group(1).split()]
        assert body
        task=lookup[row['task_id']];code=assemble(body,task.get('constants')or constants(task['task']),'asm')
        label=bool(check_task(vm,code,task)['pass']);assert label==row['grader_current_correct']
        extra.append({'id':f'trajectory:{i}','task_id':task['id'],'prompt':executed_prompt(task,code,vm),
                      'code':code,'label':int(label),'origin':'student_trajectory','split':'train','expected_values_in_prompt':False})
    sets['train']+=extra;save_jsonl(ROOT/'train.jsonl',sets['train'])
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    ids=[tokenizer.encode(x,add_special_tokens=False)for x in ['d','t']];assert all(len(x)==1 for x in ids)
    write(ROOT/'output-token-ids.json',[ids[0][0],ids[1][0]])
    for part,rows in sets.items():
        over=[r['id']for r in rows if len(tokenizer.encode(r['prompt'],add_special_tokens=False))>1024]
        assert not over,(part,over[:4])
    shutil.copytree(CODER/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'steps_each':2000,'validation_interval':400,'effective_batch':128,'context':1024,'lr':{'slow':2e-5,'fast':5e-5},
            'source':'harness-debug-v3/selected-budget','balanced_binary_batches':True,'all_input_embeddings_frozen':True,
            'source_coder_unchanged':True,'qualification':'zero validation false accepts, >=80% true positive coverage',
            'fresh_used_for_selection':False,'critic_output':'single next token d(correct) or t(wrong)',
            'memory':'one model image and KV cache at a time; coder/critic can be loaded sequentially from SD'}
    write(ROOT/'policy.json',policy)
    frozen={'counts':{k:len(v)for k,v in sets.items()},'before_optimizer_updates':True,
      'initial_master_sha256':sha(INITIAL/'model.safetensors'),'initial_packet_sha256':sha(INITIAL_PACKET),
      'files':{n:sha(ROOT/n)for n in ['train.jsonl','validation.jsonl','fresh.jsonl','output-token-ids.json','policy.json']},
      'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
      'oracle_values_in_runtime_input':False,'synthetic_not_independent_human_benchmark':True,
      'source_tasks_have_prior_exposure_but_no_fresh_labels_used_for_critic_training':True}
    write(ROOT/'data-frozen.json',frozen);print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','private_core_files']}),flush=True)


if __name__=='__main__':main()
