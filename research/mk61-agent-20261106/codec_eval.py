"""Actual compact-head Q4 generations, lossless decoding, and unchanged MK61 grading."""
import argparse
import collections
import json
import re
import time

import torch

from codec_common import ROOT,ARMS,MODES,read,protocol,allowed_ids,compact_head,sha,OLD_VOCAB
from course_common import calc_prompt,program_prompt,parse_prefix
from course_eval import grading_tasks
from emulator import Emulator
from harness import check_program,extract_code,close_number,agent_run
from native_context import wrap
from prompt_variants import without_public_examples
from tasks import BUILD,registers_used,value_of


def generate_batch(model,tokenizer,prompts,p,*,max_new=128,hide_public_inputs=False,**ignored):
    encoded=[]
    for text in prompts:
        if hide_public_inputs:text=without_public_examples(text)
        text=re.sub(r'<plan>.*?</plan>','',text,flags=re.S)
        encoded.append(tokenizer.encode(p.encode_text(text),add_special_tokens=False))
    length=max(map(len,encoded));limit=min(max_new,model.config.max_position_embeddings-length)
    if limit<=0:raise ValueError('Prompt fills context; never truncate the condition')
    device=next(model.parameters()).device
    ids=torch.full((len(encoded),length),tokenizer.pad_token_id or 0,dtype=torch.long,device=device);mask=torch.zeros_like(ids)
    for i,row in enumerate(encoded):ids[i,-len(row):]=torch.tensor(row,device=device);mask[i,-len(row):]=1
    if device.type=='cuda':torch.cuda.synchronize()
    start=time.perf_counter()
    with torch.inference_mode():out=model.generate(input_ids=ids,attention_mask=mask,max_new_tokens=limit,do_sample=False,
      use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
    if device.type=='cuda':torch.cuda.synchronize()
    seconds=time.perf_counter()-start;rows=[]
    for source,tokens in zip(encoded,out[:,length:].tolist()):
        if tokenizer.eos_token_id in tokens:tokens=tokens[:tokens.index(tokenizer.eos_token_id)]
        raw=tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False)
        reply,error=p.decode_reply(raw)
        rows.append({'raw_reply':raw,'reply':reply,'codec_error':error,'generated_token_ids':tokens,
          'generated_tokens':len(tokens),'input_tokens':len(source),'batch_generation_seconds':seconds,'batch_size':len(encoded)})
    return rows


def language_cases(model,tokenizer,tasks,p,context=512,*,audit=False):
    tasks=grading_tasks(tasks);em=Emulator();parses=[];programs=[];model.eval()
    texts=[wrap(t['task'],tokenizer,context,6114508+i,audit=audit)for i,t in enumerate(tasks)]
    for at in range(0,len(tasks),8):
        batch=tasks[at:at+8];words=texts[at:at+8]
        parsed=generate_batch(model,tokenizer,[calc_prompt(x)for x in words],p,max_new=64)
        prompts=[program_prompt({**t,'task':x})for t,x in zip(batch,words)]
        replies=generate_batch(model,tokenizer,prompts,p,max_new=160)
        for task,parse,row,prompt in zip(batch,parsed,replies,prompts):
            match=re.search(r'<calc>(.*?)</calc>',parse['reply'],re.S)
            try:
                expr=parse_prefix(match.group(1))if match else None
                passed=expr is not None and registers_used(expr)<=registers_used(task['expression'])and all(
                  close_number(str(value_of(expr,c['registers'])),c['expected_X'])for c in task['public_tests']+task['hidden_tests'])
            except (ValueError,TypeError,AttributeError,ArithmeticError):expr=None;passed=False
            parses.append({'id':task['id'],'pass':bool(passed),'parsed':expr,**parse})
            code=extract_code(row['reply']);valid=bool(code and'<run/>'in row['reply']and row['codec_error']is None)
            result=check_program(em,code,task['public_tests']+task['hidden_tests'])if valid else{'pass':False}
            programs.append({'id':task['id'],'pass':result['pass'],'valid_program_call':valid,'code':code,'result':result,'prompt':prompt,**row})
    def compact(rows):
        return {'passed':sum(x['pass']for x in rows),'total':len(rows),'rate':sum(x['pass']for x in rows)/max(1,len(rows)),
          'generated_tokens':sum(x['generated_tokens']for x in rows),'details':rows}
    return {'parse':compact(parses),'program':{**compact(programs),'valid_program_calls':sum(x['valid_program_call']for x in programs),
      'codec_errors':sum(x['codec_error']is not None for x in programs)},'context':context}


def formal_eval(model,tokenizer,tasks,p):
    import evaluate_batched
    previous=evaluate_batched.generate_many
    def adapted(m,t,prompts,**kwargs):return [x['reply']for x in generate_batch(m,t,prompts,p,**kwargs)]
    evaluate_batched.generate_many=adapted
    try:return evaluate_batched.evaluate(model,tokenizer,tasks,plan=False,max_new=160,batch_size=20)
    finally:evaluate_batched.generate_many=previous


def panel(model,tokenizer,p,*,fresh=False):
    sets={f'manual{level}':read(ROOT/(('fresh'if fresh else'development')+str(level)+'.jsonl'))for level in [1,2,3]}
    if not fresh:
        teacher=read(ROOT/'teacher-development.jsonl')
        for level in [2,3]:sets['teacher'+str(level)]=[t for t in teacher if t['level']==level]
    result={name:language_cases(model,tokenizer,tasks,p,audit=fresh)for name,tasks in sets.items()}
    result['formal']=formal_eval(model,tokenizer,read(ROOT/'formal-development.jsonl'),p)
    long=[]
    for name in ['manual2','manual3']:
        groups=collections.defaultdict(list)
        for task in sets[name]:groups[task['expression'][0]].append(task)
        long += [values[0]for values in groups.values()][:7]
    for context in [1024,2048]:result['context'+str(context)]=language_cases(model,tokenizer,long,p,context,audit=fresh)
    return result


def summary(result):
    return {name:({kind:{key:value[kind][key]for key in ['passed','total','rate','generated_tokens']}for kind in ['parse','program']}
      if name!='formal'else{'passed':value['passed'],'total':value['total'],'rate':value['pass_rate']})for name,value in result.items()}


def key_for(result):
    prog=[result['manual'+str(i)]['program']['rate']for i in [1,2,3]]
    parse=[result['manual'+str(i)]['parse']['rate']for i in [1,2,3]]
    return [result['formal']['pass_rate']>=.95,sum(prog)/3,min(prog),sum(parse)/3,
      min(result[x]['program']['rate']for x in ['context1024','context2048']),result['formal']['pass_rate']]


def language_nll(model):
    import numpy as np
    import torch.nn.functional as F
    stream=np.memmap(BUILD/'native-mixed-v1/language/validation.u16',mode='r',dtype='<u2')
    device=next(model.parameters()).device;values=[]
    with torch.inference_mode():
        weight=model.get_input_embeddings().weight[:OLD_VOCAB]
        for i in range(16):
            start=i*512;ids=torch.tensor(stream[start:start+513].astype('int64'),device=device)
            hidden=model.model(input_ids=ids[:-1][None],use_cache=False).last_hidden_state
            logits=F.linear(hidden,weight).float()
            values.append(float(F.cross_entropy(logits.reshape(-1,OLD_VOCAB),ids[1:])))
    return {'nll':sum(values)/len(values),'tokens':16*512,'output_rows':OLD_VOCAB,'same_frozen_public_language_segments':True}


def main():
    from pathlib import Path
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from lowbit import load
    a=argparse.ArgumentParser();a.add_argument('--arm',choices=ARMS,required=True);a.add_argument('--mode',choices=MODES,required=True)
    a.add_argument('--model',type=Path,required=True);a.add_argument('--packet',type=Path);a.add_argument('--label',required=True);args=a.parse_args()
    assert(ROOT/'preselected.json').exists(),'Freeze choices before any new audit'
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.02)
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    output=ROOT/'results';output.mkdir(exist_ok=True);packet=output/(args.label+'.mkqb')
    if args.packet:
        import shutil
        shutil.copyfile(args.packet,packet);load(model,packet)
    else:
        from native_quant import attach,packed_copy
        attach(model,'q4');replica,report=packed_copy(model,packet,'q4');model=replica
    model.to('cuda').eval();compact_head(model,allowed_ids(args.mode));p=protocol(args.mode)
    result=panel(model,tokenizer,p,fresh=True)
    tasks=grading_tasks([t for level in [1,2,3]for t in read(ROOT/f'fresh{level}.jsonl')]);em=Emulator();rollouts=[];raw=[]
    initial={row['id']:row for name in ['manual1','manual2','manual3']for row in result[name]['program']['details']}
    for task in tasks:
        consumed=False
        def generate(prompt):
            nonlocal consumed
            if not consumed:consumed=True;return initial[task['id']]['reply']
            row=generate_batch(model,tokenizer,[prompt],p,max_new=160,hide_public_inputs=True)[0]
            raw.append({'id':task['id'],**row});return row['reply']
        rollouts.append(agent_run(task,generate,em,turns=3,examples=False))
    formal=formal_eval(model,tokenizer,read(BUILD/'tasks/test-extended-v2.jsonl'),p)
    report={'arm':args.arm,'mode':args.mode,'label':args.label,'model':str(args.model),'packed_sha256':sha(packet),
      'metrics':result,'summary':summary(result),'full_formal':formal,'public_language':language_nll(model),
      'tool_rollouts':{'passed':sum(x['pass']for x in rollouts),'total':len(rollouts),'details':rollouts,'raw_retry_replies':raw,
        'hidden_cases_used_for_feedback':False,'automatic_search':False},
      'compact_output_rows':len(allowed_ids(args.mode)),'new_fresh_used_for_selection':False,'external_compiler_at_inference':False,
      'decoder_is_lossless_format_conversion_only':True,'native_picocalc_measured':False}
    (output/(args.label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'label':args.label,'summary':report['summary'],'tools':report['tool_rollouts']['passed'],'formal':formal['passed']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
