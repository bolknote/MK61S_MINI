"""Frozen first-shot compiler; actual tool rollouts, no hidden-answer feedback."""
import argparse
import collections
import json
import random
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer
from ac_common import ROOT,INITIAL,INITIAL_PACKET,SOURCE,ACTIONS,ACTION_IDS,END,read,write,sha,body_ids,output_ids,compact_head,MAX_TURNS
from ac_protocol import prompt_ids,header_ids,NO_BODY,decode,as_xml
from ac_model import Agent,action_weight
from ac_runtime import Session
from ac_teacher import make_session,grade,step_row
from ab_eval import BodyGrammar
from ha_protocol import encode,assemble,constants,parse_call
from hf_runtime import prompt as old_prompt
from full_isa_vm import FullVM
from lowbit import load
from tasks import save_jsonl


def generate(model,tokenizer,prompts,*,forced_action=None,sample=False):
    prompts=[p if p.endswith('<')else p+'<'for p in prompts];encoded=[prompt_ids(tokenizer,p)for p in prompts]
    rows=[None]*len(prompts);valid=[i for i,x in enumerate(encoded)if len(x)<1016]
    for i in set(range(len(rows)))-set(valid):
        rows[i]={'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[],'input_tokens':len(encoded[i])}
    if not valid:return rows
    device=next(model.parameters()).device;n=max(len(encoded[i])for i in valid)
    ids=torch.zeros((len(valid),n),dtype=torch.long,device=device);mask=torch.zeros_like(ids)
    for j,i in enumerate(valid):ids[j,:len(encoded[i])]=torch.tensor(encoded[i],device=device);mask[j,:len(encoded[i])]=1
    with torch.inference_mode():
        hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
        selected=hidden[torch.arange(len(ids),device=device),mask.sum(1)-1]
        logits=F.linear(selected,action_weight(model)).float()
        acts=(torch.multinomial((logits/.8).softmax(-1),1).flatten()if sample else logits.argmax(-1)).tolist()
    if forced_action is not None:acts=[ACTIONS.index(forced_action)]*len(valid)
    for act in sorted(set(acts)):
        action=ACTIONS[act];indexes=[i for j,i in enumerate(valid)if acts[j]==act]
        if action in NO_BODY:
            for i in indexes:rows[i]={'action':action,'body':[],'codec_error':None,'generated_token_ids':[ACTION_IDS[act]],'input_tokens':len(encoded[i])}
            continue
        prefixes=[encoded[i]+header_ids(tokenizer,action)for i in indexes];length=max(map(len,prefixes))
        values=torch.zeros((len(prefixes),length),dtype=torch.long,device=device);attention=torch.zeros_like(values)
        for j,p in enumerate(prefixes):values[j,-len(p):]=torch.tensor(p,device=device);attention[j,-len(p):]=1
        from transformers import LogitsProcessorList
        args={'temperature':.8,'top_p':.95}if sample else{}
        with torch.inference_mode():
            out=model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(511,1024-length),
                do_sample=sample,use_cache=True,pad_token_id=0,eos_token_id=END,
                logits_processor=LogitsProcessorList([BodyGrammar(tokenizer,length,action)]),**args)
        for j,i in enumerate(indexes):
            tail=out[j,length:].tolist();ended=END in tail
            if ended:tail=tail[:tail.index(END)]
            tokens=[ACTION_IDS[act],*tail]
            try:
                if not ended:raise ValueError('incomplete')
                name,body=decode(tokenizer,tokens);error=None
            except ValueError as e:name=None;body=[];error=str(e)
            rows[i]={'action':name,'body':body,'codec_error':error,'generated_token_ids':tokens,'input_tokens':len(encoded[i])}
    return rows


def compiler_model(device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(model,INITIAL_PACKET)
    model.to(device).eval();compact_head(model,json.loads((SOURCE/'output-token-ids.json').read_text()))
    return model,AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)


def compiler_evaluate(model,tokenizer,tasks):
    import hf_eval
    return hf_eval.evaluate(model,tokenizer,tasks)


def stats(rows):
    n=len(rows)
    return {'total':n,'passed':sum(r['pass']for r in rows),'false_DONE':sum(r['finished']and not r['program_correct']for r in rows),
            'premature_DONE':sum(r['finished']and not r['eligible']for r in rows),
            'repaired':sum(r['pass']and not r['initially_correct']for r in rows),
            'initially_wrong':sum(not r['initially_correct']for r in rows),
            'correct_controls':sum(r['initially_correct']for r in rows),
            'correct_controls_completed':sum(r['pass']and r['initially_correct']for r in rows),
            'abstained':sum(r['abstained']for r in rows),'unfinished_correct':sum(r['program_correct']and not r['finished']for r in rows),
            'actions':dict(collections.Counter(h['kind']for r in rows for h in r['history']))}


def tool_panel(model,tokenizer,tasks,seeds,*,legacy=False,mine=False,compiler=None,from_scratch=False):
    vm=FullVM();lookup={t['id']:t for t in tasks};rows=[];lessons=[];preferences=[];seen=set()
    for at in range(0,len(seeds),24):
        items=seeds[at:at+24];sessions=[]
        if from_scratch:
            from hf_eval import generate as old_generate
            prompts=[old_prompt(lookup[item['task_id']])for item in items]
            first=old_generate(compiler,tokenizer,prompts)
        for j,item in enumerate(items):
            task=lookup[item['task_id']]
            if from_scratch:
                s=Session(task,'asm',vm=vm,gate=False);s.initial_history=0
                try:
                    action,body=parse_call(first[j]['reply']);assert action=='write';s.apply_action(action,body)
                except (ValueError,AssertionError):s.history.append({'kind':'compiler_error'});s.exhausted=True
            else:s=make_session(task,item,vm)
            if not hasattr(s,'exhausted'):s.exhausted=False
            sessions.append(s)
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not s.exhausted and len(s.history)-s.initial_history<MAX_TURNS]
            if not active:break
            if legacy:
                import hf_eval
                prompts=[old_prompt(s.task,current=s.body,observation=s.observation,case=s.case,revision=s.revision,runs=s.runs)for s in active]
                generations=hf_eval.generate(model,tokenizer,prompts)
                for s,g in zip(active,generations):
                    try:
                        a,b=parse_call(g['reply'],s.body);g['legacy_action']=a
                        g['action']='write'if a=='patch'else a;g['body']=b or[]
                    except ValueError:g['action']=None;g['body']=[];g['codec_error']='parse'
            else:
                prompts=[s.request()for s in active];generations=generate(model,tokenizer,prompts)
            for s,p,g in zip(active,prompts,generations):
                if mine and p not in seen:
                    row=step_row(s,'current_student');row.update(model_action=g.get('action'),
                        actual_false_DONE=g.get('action')=='done'and not grade(s))
                    lessons.append(row);seen.add(p)
                if g['codec_error']:
                    s.history.append({'kind':'generation_error','prompt':p,'generation':g});s.exhausted=True;continue
                kind=s.apply_action(g['action'],g['body']);s.history[-1].update(prompt=p,generation=g)
        for item,s in zip(items,sessions):
            correct=grade(s);eligible=s.eligibility()[0]
            rows.append({'id':s.task['id'],'level':s.task.get('level',1),'initially_correct':False if from_scratch else item['intentionally_correct'],
                         'program_correct':correct,'finished':s.finished,'eligible':eligible,'pass':correct and s.finished and eligible,
                         'abstained':s.abstained,'body':s.body,'cases':len(s.task['public_tests']),'history':s.history})
    simple=[r for r in rows if r['level']==1]
    panel={**stats(rows),'simple':stats(simple),'by_public_count':{str(n):stats([r for r in rows if r['cases']==n])for n in range(1,5)},
           'reference_in_runtime':False,'gate_enabled':False,'details':rows}
    return panel,lessons


def development(model,tokenizer):
    tasks=read(ROOT/'validation.jsonl');items=read(ROOT/'validation-seeds.jsonl')
    panel,_=tool_panel(model,tokenizer,tasks,items)
    twins,_=tool_panel(model,tokenizer,read(ROOT/'validation-goal-twins.jsonl'),read(ROOT/'validation-twin-seeds.jsonl'))
    return {'tools':panel,'goal_twins':twins}


def advance(result):
    t=result['tools']['simple']
    return t['false_DONE']==0 and t['repaired']/max(1,t['initially_wrong'])>=.9 and t['correct_controls_completed']/max(1,t['correct_controls'])>=.95


def selection(result):
    t=result['tools'];s=t['simple']
    ready=t['false_DONE']==0 and t['passed']/max(1,t['total'])>=.8
    return [ready,advance(result),(t['passed']-2*t['false_DONE'])/t['total'],-t['false_DONE'],t['passed'],result['goal_twins']['passed']]


def brief(result):
    return {k:{n:v for n,v in r.items()if n!='details'}for k,r in result.items()}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--action',choices=['baseline','audit','mine'],required=True);ap.add_argument('--arm');ap.add_argument('--block',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.4);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='baseline':
        model,t=compiler_model();result={}
        for split in ['validation','fresh']if(ROOT/'preselected.json').exists()else['validation']:
            result[split]=tool_panel(model,t,read(ROOT/(split+'.jsonl')),read(ROOT/(split+'-seeds.jsonl')),legacy=True)[0]
        write(ROOT/'baseline.json',result);return
    folder=ROOT/a.arm
    from ac_model import Agent
    agent=Agent(checkpoint=folder/'last.safetensors'if a.action=='mine'else folder/'best.safetensors')
    model,_=agent.packed(folder/('mining.mkqb'if a.action=='mine'else'audit.mkqb'));model.to('cuda').eval();t=agent.tokenizer;compact_head(model,output_ids(t));del agent
    if a.action=='mine':
        from ac_mine import mine
        mine(model,t,a.arm,a.block);return
    assert(ROOT/'preselected.json').exists()
    tasks=read(ROOT/'fresh.jsonl');items=read(ROOT/'fresh-seeds.jsonl');base,unused=compiler_model()
    result={'tools':tool_panel(model,t,tasks,items)[0],
            'goal_twins':tool_panel(model,t,read(ROOT/'fresh-goal-twins.jsonl'),read(ROOT/'fresh-twin-seeds.jsonl'))[0],
            'from_scratch':tool_panel(model,t,tasks[:64],[{'task_id':x['id']}for x in tasks[:64]],compiler=base,from_scratch=True)[0],
            'compiler_language':compiler_evaluate(base,t,tasks),'fresh_used_for_selection':False,
            'tool_packet_sha256':sha(folder/'audit.mkqb')}
    write(ROOT/(a.arm+'-audit.json'),result)
    print(json.dumps({'arm':a.arm,'tools':stats(result['tools']['details']),'compiler_language':result['compiler_language']['passed']}),flush=True)


if __name__=='__main__':main()
