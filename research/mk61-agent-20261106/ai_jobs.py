"""Bounded GPU evaluation and aggregation of verified student repair examples."""
import argparse
import json
import random
import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM,AutoTokenizer
from ai_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,PANELS,read,write,sha,output_ids,compact_head
from ai_model import Agent
from ai_eval import panel,generate,score,calibrated_threshold,release
from ai_teacher import make_session,row,correct
from full_isa_vm import FullVM
from ha_protocol import encode,assemble
from tasks import save_jsonl


def load_model(arm,which):
    agent=Agent(arm,checkpoint=None if arm=='initial'else ROOT/arm/(which+'.safetensors'))
    folder=ROOT/arm;folder.mkdir(exist_ok=True)
    model,_=agent.packed(folder/('mining.mkqb'if which=='last'else'audit.mkqb'))
    model.cuda().eval();tokenizer=agent.tokenizer;compact_head(model,output_ids(tokenizer));return model,tokenizer


def mine(model,tokenizer,arm,block):
    tasks=read(ROOT/'train.jsonl');lookup={t['id']:t for t in tasks}
    seeds=read(ROOT/'train-new-seeds.jsonl')+read(ROOT/'train-skill-seeds.jsonl');rng=random.Random(1214801+block);rng.shuffle(seeds);items=seeds[:96]
    errors=read(ROOT/'reproduction-seeds.jsonl');rng.shuffle(errors);items+=errors[:32]
    completion=read(ROOT/'train-new.jsonl');rng.shuffle(completion)
    for i,t in enumerate(completion[:32]):
        n=[2,4,6][i%3];items.append({'task_id':t['id'],'initial_code':t['reference_code'],'candidate_code':t['reference_code'],
            'prefill_revision':n,'consume_prefill_actions':n,'pre_run_all':bool(i%2),'intentionally_correct':True})
    result,lessons=panel(model,tokenizer,tasks,items,mine=True)
    dev=ROOT/arm/f'development-{block}.json'
    if not dev.exists():dev=ROOT/'initial-development-audit.json'
    threshold=json.loads(dev.read_text())['threshold']
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
       'raw_false_DONE':result['false_DONE'],'gated_false_DONE':None,'training_only':True})
    print(json.dumps({'arm':arm,'block':block,'lessons':len(lessons),'verified_alternatives':alternative}),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--action',choices=['mine','baseline','audit'],required=True);ap.add_argument('--arm',default='initial');ap.add_argument('--block',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.75);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='mine':
        model,t=load_model(a.arm,'last');mine(model,t,a.arm,a.block);return
    model,t=load_model(a.arm,'best');split='fresh'if a.action=='audit'or(ROOT/'preselected.json').exists()else'development'
    if a.action=='audit':assert(ROOT/'preselected.json').exists()
    result={};threshold=None if a.arm=='initial'else json.loads((ROOT/a.arm/'best.json').read_text())['threshold']
    for part,taskfile,seedfile in PANELS:
        tasks=read(ROOT/taskfile.format(split=split));seeds=read(ROOT/seedfile.format(split=split))
        result[part]={'raw':panel(model,t,tasks,seeds)[0]}
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
        result['reproduction']={'raw':panel(model,t,read(ROOT/'reproduction.jsonl'),read(ROOT/'reproduction-seeds.jsonl'))[0]}
    if split=='development':
        result['key']=score(*[result[n]['raw']for n,_,_ in PANELS])
        result['release_eligible']=release(*[result[n]['raw']for n,_,_ in PANELS])
        threshold=calibrated_threshold([r for name,_,_ in PANELS for r in result[name]['raw']['calibration']])
    result.update(split=split,threshold=threshold,exam_used_for_selection=False,packet_sha256=sha(ROOT/a.arm/'audit.mkqb'))
    write(ROOT/(a.arm+'-'+split+'-audit.json'),result)
    print(json.dumps({'arm':a.arm,'split':split,'main':{mode:{k:v for k,v in report.items()if k not in ['details','calibration','simple','actions']}for mode,report in result['main'].items()}}),flush=True)


if __name__=='__main__':main()
