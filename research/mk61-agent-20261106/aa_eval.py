"""Raw model decisions, independent semantic grading, and training-only mining."""
import argparse
import collections
import json
import time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from aa_common import ROOT, SOURCE, INITIAL, INITIAL_PACKET, ACTION_IDS, CONTEXT, MAX_TURNS, read, write, sha, compact_head, output_ids
from aa_protocol import Grammar, decode, as_xml
from aa_runtime import Session
from aa_teacher import lesson, grade
from ha_protocol import encode, constants
from full_isa_vm import FullVM
from lowbit import load
from tasks import save_jsonl


def generate(model, tokenizer, prompts):
    prompts=[p if p.endswith('<') else p+'<' for p in prompts]
    encoded=[tokenizer.encode(p,add_special_tokens=False)for p in prompts]
    rows=[None]*len(prompts)
    valid=[i for i,p in enumerate(encoded)if len(p)<CONTEXT-1]
    for i in set(range(len(prompts)))-set(valid):
        rows[i]={'action':None,'body':[],'reply':'','codec_error':'context_overflow','generated_token_ids':[],
                 'generated_tokens':0,'input_tokens':len(encoded[i])}
    if not valid:return rows
    length=max(len(encoded[i])for i in valid);device=next(model.parameters()).device
    ids=torch.full((len(valid),length),tokenizer.pad_token_id or 0,dtype=torch.long,device=device);mask=torch.zeros_like(ids)
    for j,i in enumerate(valid):
        ids[j,-len(encoded[i]):]=torch.tensor(encoded[i],device=device);mask[j,-len(encoded[i]):]=1
    started=time.monotonic()
    with torch.inference_mode():
        out=model.generate(input_ids=ids,attention_mask=mask,max_new_tokens=min(512,CONTEXT-length),do_sample=False,
                           use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id,
                           logits_processor=LogitsProcessorList([Grammar(tokenizer,length)]))
    for j,i in enumerate(valid):
        tokens=out[j,length:].tolist()
        if tokenizer.eos_token_id in tokens:tokens=tokens[:tokens.index(tokenizer.eos_token_id)]
        try:
            action,body=decode(tokenizer,tokens)
            reply=as_xml(action,body)if action not in ['diag','unsure']else action.upper()+' '+' '.join(f'{b:02X}'for b in body)
            error=None
        except ValueError as e:action=None;body=[];reply='';error=str(e)
        rows[i]={'action':action,'body':body,'reply':reply,'raw_reply':reply,'codec_error':error,'generated_token_ids':tokens,
                 'generated_tokens':len(tokens),'input_tokens':len(encoded[i]),'batch_size':len(valid),
                 'batch_generation_seconds':time.monotonic()-started}
    return rows


def evaluate(model,tokenizer,tasks):
    import hf_eval
    old=hf_eval.generate;hf_eval.generate=generate
    try:
        result=hf_eval.evaluate(model,tokenizer,tasks)
        for row in result['details']:
            if not row['prompt'].endswith('<'):row['prompt']+='<'
        return result
    finally:hf_eval.generate=old


def tool_panel(model,tokenizer,tasks,seeds,*,mine=False,from_scratch=False):
    vm=FullVM();lookup={t['id']:t for t in tasks};rows=[];lessons=[];seen=set()
    for at in range(0,len(seeds),24):
        items=seeds[at:at+24];sessions=[]
        for item in items:
            t=lookup[item['task_id']];body=None if from_scratch else encode(item['initial_code'],constants(t['task']),'asm')
            s=Session(t,'asm',body=body,vm=vm,gate=False);s.exhausted=False
            if body is not None:
                s.run(0)
                if item.get('pre_run_all'):
                    for i in range(1,len(t['public_tests'])):s.run(i)
            sessions.append(s)
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not s.exhausted]
            if not active:break
            prompts=[s.request()for s in active]
            for s,p,g in zip(active,prompts,generate(model,tokenizer,prompts)):
                if mine:
                    row=lesson(s,'on_policy',tokenizer)
                    if row is not None and p not in seen:
                        row.update(model_action=g['action'],actual_false_DONE=g['action']=='done'and not grade(s),
                                   public_cases=len(s.task['public_tests']))
                        lessons.append(row);seen.add(p)
                if g['codec_error']:
                    s.history.append({'kind':'context_overflow'if g['codec_error']=='context_overflow'else'error',
                                      'prompt':p,'generation':g});s.exhausted=True;continue
                kind=s.apply_action(g['action'],g['body']);entry=s.history[-1]
                entry.update(prompt=p,generation=g)
                if kind=='done':entry['grader_program_correct_at_attempt']=grade(s)
        for item,s in zip(items,sessions):
            correct=grade(s)
            eligible,missing,failed=s.eligibility()
            rows.append({'id':s.task['id'],'initially_correct':item['intentionally_correct']if not from_scratch else False,
                         'pass':correct and s.finished and eligible,'program_correct':correct,'finished':s.finished,'abstained':s.abstained,
                         'all_public_cases_executed_and_stopped':eligible,'missing_cases':missing,'failed_cases':failed,
                         'public_cases':len(s.task['public_tests']),'body':s.body,'history':s.history})
    def stats(values):
        return {'total':len(values),'passed':sum(r['pass']for r in values),
                'false_DONE':sum(r['finished']and not r['program_correct']for r in values),
                'premature_DONE':sum(r['finished']and not r['all_public_cases_executed_and_stopped']for r in values),
                'abstained':sum(r['abstained']for r in values)}
    result={**stats(rows),'initially_wrong':sum(not r['initially_correct']for r in rows),
            'repaired':sum(r['pass']and not r['initially_correct']for r in rows),
            'unfinished_correct':sum(r['program_correct']and not r['finished']for r in rows),
            'by_public_count':{str(n):stats([r for r in rows if r['public_cases']==n])for n in range(1,5)},
            'actions':dict(collections.Counter(h['kind']for r in rows for h in r['history'])),
            'gate_enabled':False,'reference_answers_in_feedback':False,'details':rows}
    return result,lessons


def documented():
    return [t for t in read(ROOT/'isa-audit.jsonl')if t['kind']=='primitive'and t['catalog_risk']=='documented']


def development(model,tokenizer):
    tasks=read(ROOT/'validation.jsonl')
    return {'language':evaluate(model,tokenizer,tasks),'isa':evaluate(model,tokenizer,documented()),
            'legacy':evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl')),
            'tools':tool_panel(model,tokenizer,tasks,read(ROOT/'validation-seeds.jsonl'))[0]}


def selection(result):
    t=result['tools'];retained=result['isa']['passed']==648 and result['legacy']['passed']>=66
    eligible=retained and t['false_DONE']==0 and t['passed']/t['total']>=.8
    return [eligible,retained,(t['passed']-2*t['false_DONE'])/t['total'],-t['false_DONE'],t['passed'],
            result['legacy']['passed'],result['language']['passed']]


def brief(result):
    return {k:{n:v for n,v in r.items()if n not in ['details','by_opcode']}for k,r in result.items()}


def load_model(path,packet=None,save_packet=None):
    tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True)
    if packet:load(model,packet)
    else:
        from native_quant import attach,packed_copy
        import tempfile
        from pathlib import Path
        attach(model,'q4')
        with tempfile.TemporaryDirectory()as tmp:model,_=packed_copy(model,save_packet or Path(tmp)/'eval.mkqb','q4')
    model.to('cuda').eval();compact_head(model,output_ids(tokenizer))
    return model,tokenizer


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--action',choices=['mine','audit','baseline'],required=True)
    ap.add_argument('--arm');ap.add_argument('--stage',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.25);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='baseline':
        import hf_eval
        tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
        model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(model,INITIAL_PACKET)
        model.to('cuda').eval();compact_head(model,json.loads((SOURCE/'output-token-ids.json').read_text()))
        tasks=read(ROOT/'validation.jsonl')
        seeds=read(ROOT/'validation-seeds.jsonl')
        result={'language':hf_eval.evaluate(model,tokenizer,tasks),'isa':hf_eval.evaluate(model,tokenizer,documented()),
                'legacy':hf_eval.evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl')),
                'tools':hf_eval.tool_panel(model,tokenizer,tasks,seeds,gate=False,max_turns=MAX_TURNS)}
        write(ROOT/'old-protocol-baseline.json',result);return
    folder=ROOT/a.arm/('last'if a.action=='mine'else'best')
    model,tokenizer=load_model(folder,save_packet=ROOT/a.arm/('mining.mkqb'if a.action=='mine'else'audit.mkqb'))
    if a.action=='mine':
        tasks=read(ROOT/'training-tasks.jsonl');items=read(ROOT/'train-seeds.jsonl')
        import random
        rng=random.Random(712901+a.stage);rng.shuffle(items);items=items[:160]
        panel,lessons=tool_panel(model,tokenizer,tasks,items,mine=True)
        save_jsonl(ROOT/f'onpolicy-{a.stage}-{a.arm}.jsonl',lessons)
        write(ROOT/f'mining-{a.stage}-{a.arm}.json',panel)
        print(json.dumps({'mining_stage':a.stage,'arm':a.arm,'lessons':len(lessons),'false_DONE':panel['false_DONE'],
                          'unique_false_DONE_states':sum(r['actual_false_DONE']for r in lessons)}),flush=True)
    else:
        assert (ROOT/'preselected.json').exists()
        tasks=read(ROOT/'fresh.jsonl')
        result={'language':evaluate(model,tokenizer,tasks),'isa':evaluate(model,tokenizer,documented()),
                'legacy':evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl')),
                'tools':tool_panel(model,tokenizer,tasks,read(ROOT/'fresh-seeds.jsonl'))[0],
                'from_scratch':tool_panel(model,tokenizer,tasks[:64],
                    [{'task_id':t['id'],'initial_code':[],'intentionally_correct':False}for t in tasks[:64]],from_scratch=True)[0],
                'fresh_used_for_selection':False,'packed_sha256':sha(ROOT/a.arm/'audit.mkqb'),'physical_picocalc_measured':False}
        write(ROOT/(a.arm+'-audit.json'),result);print(json.dumps(brief(result)),flush=True)


if __name__=='__main__':main()
