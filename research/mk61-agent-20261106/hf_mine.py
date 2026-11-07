"""Relabel states visited by the fixed student; references stay outside tools."""
import collections
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from hf_common import ROOT,INITIAL,INITIAL_PACKET,read,sha,write,allowed,compact_head
from hf_runtime import Session
from hf_eval import tool_panel
from ha_protocol import constants,encode,assemble,write_call
from full_isa_vm import FullVM,check_task
from lowbit import load
from tasks import save_jsonl


def main():
    if(ROOT/'mining.json').exists():return
    stage=json.loads((ROOT/'data-stage.json').read_text())
    for n,d in stage['files'].items():assert sha(ROOT/n)==d
    assert sha(INITIAL/'model.safetensors')==stage['initial_master_sha256']and sha(INITIAL_PACKET)==stage['initial_packet_sha256']
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False);load(model,INITIAL_PACKET)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False);model.to('cuda').eval();compact_head(model,allowed())
    tasks=read(ROOT/'train.jsonl');lookup={t['id']:t for t in tasks};items=read(ROOT/'mining-seeds.jsonl')
    assert all(t['split']=='train'for t in tasks)
    panel=tool_panel(model,tokenizer,tasks,items,gate=False);write(ROOT/'mining-rollouts.json',panel)
    vm=FullVM();lessons=[];seen=set();counts=collections.Counter()
    for i,(item,rollout)in enumerate(zip(items,panel['details'])):
        task=lookup[item['task_id']];pool=task.get('constants')or constants(task['task'])
        s=Session(task,'asm',body=encode(item['initial_code'],pool,'asm'),vm=vm,gate=False);s.run(0)
        if item.get('pre_run_all'):
            for index in range(1,len(task['public_tests'])):s.run(index)
        for turn,entry in enumerate(rollout['history']):
            if entry['kind']=='context_overflow':break
            text=s.request();assert text==entry['prompt']
            try:correct=check_task(vm,assemble(s.body,pool,'asm'),task)['pass']if s.body else False
            except (ValueError,RuntimeError,ArithmeticError):correct=False
            if not correct:answer=write_call(encode(task['reference_code'],pool,'asm'));bucket='wrong'
            else:
                eligible,missing,failed=s.eligibility()
                assert not failed
                if missing:answer=f'<run>{missing[0]:02X}</run>';bucket='verify'
                else:answer='<done/>';bucket='done'
            false_done=not correct and entry['kind']=='done'
            length=len(tokenizer.encode(text+answer,add_special_tokens=False))+1
            if text not in seen and length<=1024:
                seen.add(text);lessons.append({'id':f'dagger:{i}:{turn}','task_id':task['id'],'prompt':text,'answer':answer,'bucket':bucket,
                  'model_reply':entry['reply'],'model_action':entry['kind'],'wrong_DONE':bool(false_done),'grader_current_correct':bool(correct),
                  'reference_answers_in_prompt':False,'source_split':'train'})
                counts[bucket]+=1;counts['wrong_DONE']+=int(false_done)
            elif length>1024:counts['overlength_skipped']+=1
            s.apply(entry['reply'])
    assert all(counts[k]>0 for k in ['wrong','done','verify'])
    save_jsonl(ROOT/'dagger-lessons.jsonl',lessons)
    write(ROOT/'mining.json',{'source_packet_sha256':sha(INITIAL_PACKET),'seeds':len(items),'lessons':len(lessons),'counts':dict(counts),
      'train_only':True,'before_optimizer_updates':True,'oracle_answers_in_runtime_feedback':False,
      'rollouts_sha256':sha(ROOT/'mining-rollouts.json'),'lessons_sha256':sha(ROOT/'dagger-lessons.jsonl')})
    print(json.dumps({'mined':len(lessons),'counts':dict(counts)}),flush=True)


if __name__=='__main__':main()
