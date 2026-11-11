"""Bounded GPU evaluation and aggregation of verified student repair examples."""
import argparse
import json
import random
import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM,AutoTokenizer
from ae_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,read,write,sha,output_ids,compact_head
from ae_model import Agent
from ae_eval import panel,generate
from ae_teacher import make_session,row,correct
from full_isa_vm import FullVM
from ha_protocol import encode,assemble
from tasks import save_jsonl


def load_model(arm,which):
    if arm=='initial':
        model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load=__import__('lowbit').load;load(model,INITIAL_PACKET)
        model.cuda().eval();tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True);compact_head(model,output_ids(tokenizer));return model,tokenizer
    folder=ROOT/arm;agent=Agent('lora16'if arm=='warmup'else arm,checkpoint=folder/(which+'.safetensors')if arm!='warmup'else None)
    if arm=='warmup':
        with torch.no_grad():agent.correct_head.copy_(load_file(str(folder/'correct-head.safetensors'))['correct_head'].cuda())
    model,_=agent.packed(folder/('mining.mkqb'if which=='last'else'audit.mkqb'));model.cuda().eval();tokenizer=agent.tokenizer;compact_head(model,output_ids(tokenizer));return model,tokenizer


def mine(model,tokenizer,arm,block):
    tasks=read(ROOT/'train.jsonl')+read(ROOT/'train-twins.jsonl');lookup={t['id']:t for t in tasks}
    seeds=read(ROOT/'train-seeds.jsonl')+read(ROOT/'train-twin-seeds.jsonl');rng=random.Random(712701+block);rng.shuffle(seeds);items=seeds[:160]
    result,lessons=panel(model,tokenizer,tasks,items,mine=True)
    dev=ROOT/arm/f'development-{block}.json';threshold=json.loads(dev.read_text())['threshold']
    rejected,additional=panel(model,tokenizer,tasks,items[:64],threshold=threshold,mine=True);lessons+=additional
    vm=FullVM();alternative=0;sampled_errors=0
    for at in range(0,48,12):
        batch=items[at:at+12];sessions=[make_session(lookup[s['task_id']],s,vm)for s in batch]
        for repeat in range(4):
            values=generate(model,tokenizer,[s.request()for s in sessions],forced_action='write',sample=True)
            for seed,s,g in zip(batch,sessions,values):
                if g.get('codec_error')or not g.get('body'):continue
                task=lookup[seed['task_id']]
                if correct(vm,task,g['body'],s.pool):
                    if not correct(vm,task,s.body,s.pool):
                        code=assemble(g['body'],s.pool,'asm');value=row(s,task,'verified_student_alternative')
                        value.update(action='write',body=encode(code,s.pool,'asm'));lessons.append(value);alternative+=1
                else:
                    after=make_session(task,seed,vm);after.apply_action('write',g['body']);lessons.append(row(after,task,'sampled_student_error'));sampled_errors+=1
    save_jsonl(ROOT/f'onpolicy-{block}-{arm}.jsonl',lessons)
    write(ROOT/f'mining-{block}-{arm}.json',{'states':len(lessons),'verified_alternative_repairs':alternative,'sampled_error_states':sampled_errors,
       'raw_false_DONE':result['false_DONE'],'gated_false_DONE':rejected['false_DONE'],'training_only':True})
    print(json.dumps({'arm':arm,'block':block,'lessons':len(lessons),'verified_alternatives':alternative}),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--action',choices=['mine','baseline','audit'],required=True);ap.add_argument('--arm',default='initial');ap.add_argument('--block',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.75);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='mine':
        model,t=load_model(a.arm,'last');mine(model,t,a.arm,a.block);return
    model,t=load_model(a.arm,'best');split='fresh'if a.action=='audit'or(ROOT/'preselected.json').exists()else'development'
    if a.action=='audit':assert(ROOT/'preselected.json').exists()
    result={};threshold=None if a.arm=='initial'else json.loads((ROOT/a.arm/'best.json').read_text())['threshold']
    for part,taskfile,seedfile in [('main',split+'.jsonl',split+'-seeds.jsonl'),('twins',split+'-twins.jsonl',split+'-twin-seeds.jsonl'),
                                  ('binding',split+'-binding.jsonl',split+'-binding-seeds.jsonl')]:
        tasks=read(ROOT/taskfile);seeds=read(ROOT/seedfile)
        result[part]={'raw':panel(model,t,tasks,seeds)[0]}
        if threshold is not None:result[part]['calibrated']=panel(model,t,tasks,seeds,threshold=threshold)[0]
    if split=='fresh':
        from ac_eval import compiler_model
        from hf_eval import generate as compile_generate
        from hf_runtime import prompt
        from ha_protocol import parse_call
        tasks=read(ROOT/'fresh.jsonl');scratch=[t for level,n in [(1,24),(2,24),(3,16)]for t in[t for t in tasks if t['level']==level][:n]]
        path=ROOT/'scratch-compiler.json'
        if path.exists():generations=json.loads(path.read_text())
        else:
            compiler,unused=compiler_model();generations=[]
            for at in range(0,len(scratch),16):
                for g in compile_generate(compiler,t,[prompt(task)for task in scratch[at:at+16]]):
                    try:action,body=parse_call(g['reply'])
                    except ValueError:action=None;body=[]
                    g.update(action=action,body=body);generations.append(g)
            write(path,generations);del compiler
        seeds=[{'task_id':task['id'],'compiler_generation':g,'intentionally_correct':False}for task,g in zip(scratch,generations)]
        result['from_scratch']={'raw':panel(model,t,scratch,seeds)[0]}
        if threshold is not None:result['from_scratch']['calibrated']=panel(model,t,scratch,seeds,threshold=threshold)[0]
    result.update(split=split,threshold=threshold,exam_used_for_selection=False,packet_sha256=sha(INITIAL_PACKET)if a.arm=='initial'else sha(ROOT/a.arm/'audit.mkqb'))
    write(ROOT/(a.arm+'-'+split+'-audit.json'),result)
    print(json.dumps({'arm':a.arm,'split':split,'main':{mode:{k:v for k,v in report.items()if k not in ['details','calibration','simple','actions']}for mode,report in result['main'].items()}}),flush=True)


if __name__=='__main__':main()
