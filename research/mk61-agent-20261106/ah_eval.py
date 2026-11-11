"""Raw and calibrated tool rollouts, with semantics graded strictly offline."""
import argparse
import collections
import json
import torch
import torch.nn.functional as F
from transformers import LogitsProcessorList,AutoModelForCausalLM,AutoTokenizer
from ah_common import ROOT,OLD,ACTIONS,ACTION_IDS,END,CORRECT_IDS,body_ids,output_ids,compact_head,read,write,sha,public_task
from ah_model import Agent,action_weight,correct_weight
from ah_teacher import make_session,correct
from ac_protocol import prompt_ids,header_ids,decode,NO_BODY
from ab_eval import BodyGrammar
from ac_runtime import Session
from ac_eval import stats
from full_isa_vm import FullVM
from lowbit import load


def generate(model,tokenizer,prompts,forced_action=None,sample=False):
    encoded=[prompt_ids(tokenizer,p)for p in prompts];rows=[None]*len(prompts);valid=[i for i,p in enumerate(encoded)if len(p)<1016]
    for i in set(range(len(rows)))-set(valid):rows[i]={'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[],'correctness_margin':None}
    if not valid:return rows
    device=next(model.parameters()).device;n=max(len(encoded[i])for i in valid)
    ids=torch.zeros((len(valid),n),dtype=torch.long,device=device);mask=torch.zeros_like(ids)
    for j,i in enumerate(valid):ids[j,:len(encoded[i])]=torch.tensor(encoded[i],device=device);mask[j,:len(encoded[i])]=1
    with torch.inference_mode():
        h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
        selected=h[torch.arange(len(ids),device=device),mask.sum(1)-1]
        logits=F.linear(selected,action_weight(model)).float();semantic=F.linear(selected,correct_weight(model)).float()
        acts=(torch.multinomial((logits/.8).softmax(-1),1).flatten()if sample else logits.argmax(-1)).tolist()
        margins=(semantic[:,1]-semantic[:,0]).tolist()
    if forced_action:acts=[ACTIONS.index(forced_action)]*len(valid)
    for act in sorted(set(acts)):
        action=ACTIONS[act];indexes=[i for j,i in enumerate(valid)if acts[j]==act]
        if action in NO_BODY:
            for i in indexes:rows[i]={'action':action,'body':[],'codec_error':None,'generated_token_ids':[ACTION_IDS[act]]}
            continue
        prefixes=[encoded[i]+header_ids(tokenizer,action)for i in indexes];length=max(map(len,prefixes))
        values=torch.zeros((len(indexes),length),dtype=torch.long,device=device);attention=torch.zeros_like(values)
        for j,p in enumerate(prefixes):values[j,-len(p):]=torch.tensor(p,device=device);attention[j,-len(p):]=1
        with torch.inference_mode():
            result=model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(511,1024-length),
               do_sample=sample,use_cache=True,pad_token_id=0,eos_token_id=END,
               logits_processor=LogitsProcessorList([BodyGrammar(tokenizer,length,action)]),**({'temperature':.8,'top_p':.95}if sample else{}))
        for j,i in enumerate(indexes):
            tail=result[j,length:].tolist();ended=END in tail
            if ended:tail=tail[:tail.index(END)]
            tokens=[ACTION_IDS[act],*tail]
            try:
                if not ended:raise ValueError('incomplete')
                a,b=decode(tokenizer,tokens);error=None
            except ValueError as e:a=None;b=[];error=str(e)
            rows[i]={'action':a,'body':b,'codec_error':error,'generated_token_ids':tokens}
    for j,i in enumerate(valid):rows[i].update(correctness_margin=margins[j],input_tokens=len(encoded[i]))
    return rows


def panel(model,tokenizer,tasks,seeds,*,threshold=None,mine=False):
    lookup={t['id']:t for t in tasks};vm=FullVM();rows=[];lessons=[];calibration=[]
    for at in range(0,len(seeds),24):
        items=seeds[at:at+24];sessions=[make_session(lookup[s['task_id']],s,vm)for s in items]
        for s in sessions:s.gate=threshold is not None;s.exhausted=getattr(s,'exhausted',False)
        for turn in range(10):
            active=[s for s in sessions if not s.finished and not s.abstained and not s.exhausted and len(s.history)-s.initial_history<10]
            if not active:break
            texts=[s.request()for s in active];values=generate(model,tokenizer,texts)
            for s,p,g in zip(active,texts,values):
                task=lookup[s.task['id']];snapshot={'id':task['id'],'body':list(s.body or[]),'pool':list(s.pool),
                    'margin':g['correctness_margin'],'action':g['action'],'eligible':s.eligibility()[0]}
                calibration.append(snapshot)
                if mine:
                    from ah_teacher import row
                    value=row(s,task,'current_student');value['hard_case']=not value['correctness']and g['action']=='done';lessons.append(value)
                if g.get('codec_error'):s.history.append({'kind':'generation_error','prompt':p,'generation':g});s.exhausted=True;continue
                if g['action']=='done'and threshold is not None and s.eligibility()[0]and g['correctness_margin']<threshold:
                    s.observation='Оценка решения не подтвердила соответствие условию. Проверь операцию, аргумент и требования задачи; при неуверенности выбери UNSURE.'
                    s.history.append({'kind':'semantic_DONE_rejected','prompt':p,'generation':g,'observation':s.observation,'revision':s.revision});continue
                kind=s.apply_action(g['action'],g['body']);s.history[-1].update(prompt=p,generation=g)
        for seed,s in zip(items,sessions):
            t=lookup[s.task['id']];ok=correct(vm,t,s.body,s.pool);eligible=s.eligibility()[0]
            initial_correct=correct(vm,t,seed['compiler_generation'].get('body'),s.pool)if'compiler_generation'in seed else seed['intentionally_correct']
            rows.append({'id':t['id'],'level':t.get('level',1),'initially_correct':initial_correct,
                'program_correct':ok,'finished':s.finished,'eligible':eligible,'pass':ok and s.finished and eligible,
                'abstained':s.abstained,'body':s.body,'history':s.history})
    for row in calibration:row['truth']=int(correct(vm,lookup[row['id']],row['body'],row['pool']))
    return {**stats(rows),'simple':stats([r for r in rows if r['level']==1]),'details':rows,'calibration':calibration,
       'threshold':threshold,'reference_in_runtime':False},lessons


def calibrated_threshold(examples):
    negatives=[r['margin']for r in examples if r['truth']==0 and r['margin']is not None]
    if not negatives:return 0.
    top=max(negatives);above=sorted(r['margin']for r in examples if r['truth']==1 and r['margin']is not None and r['margin']>top)
    return (top+above[0])/2 if above else top+1e-3



def release(t,s,g):return all(p['false_DONE']==0 for p in [t,s,g])and t['passed']/t['total']>=.8


def score(t,s,g,baseline=None):
    panels=[t,s,g];retained=True
    if baseline:
        for name,p in zip(['main','skills','goals'],panels):
            b=baseline[name].get('raw',baseline[name])
            retained &= p['passed']>=b['passed']and p['false_DONE']<=b['false_DONE']and p['correct_controls_completed']>=b['correct_controls_completed']
    utility=sum(w*(p['passed']-2*p['false_DONE'])/p['total']for w,p in zip([.60,.25,.15],panels))
    return [bool(retained),utility,sum(p['passed']for p in panels),-sum(p['false_DONE']for p in panels),t['passed'],s['passed'],g['passed']]


def development(model,tokenizer):
    result={}
    for name,taskfile,seedfile in [('main','development.jsonl','development-seeds.jsonl'),('skills','development-skills.jsonl','development-skill-seeds.jsonl'),('goals','development-goals.jsonl','development-goal-seeds.jsonl')]:
        result[name]=panel(model,tokenizer,read(ROOT/taskfile),read(ROOT/seedfile))[0]
    result['threshold']=calibrated_threshold([r for p in result.values()for r in p['calibration']])
    baseline=json.loads((ROOT/'initial-development-audit.json').read_text())
    result['key']=score(result['main'],result['skills'],result['goals'],baseline)
    result['release_eligible']=release(result['main'],result['skills'],result['goals'])
    return result



def brief(result):
    return {k:{n:v for n,v in value.items()if n not in ['details','calibration']}if isinstance(value,dict)else value for k,value in result.items()}
