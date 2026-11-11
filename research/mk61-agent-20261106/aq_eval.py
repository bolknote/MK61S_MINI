"""Raw neural decisions and repairs; reference programs are used only offline."""
import collections
import copy
import json
import torch
import torch.nn.functional as F
from transformers import LogitsProcessorList
from aq_common import ROOT,ACTIONS,ACTION_IDS,CORRECT_IDS,MAX_TURNS,read
from aq_model import action_weight,correct_weight
from aq_protocol import prompt_ids,header_ids,decode,NO_BODY,END,BodyGrammar
from aq_runtime import Session,render,diagnosis
from aj_teacher import correct
from full_isa_vm import FullVM


def generate(model,tokenizer,prompts,forced_action=None):
    enc=[prompt_ids(tokenizer,p)for p in prompts];rows=[None]*len(prompts)
    assert all(not set(x)&set(ACTION_IDS+CORRECT_IDS)for x in enc)
    valid=[i for i,p in enumerate(enc)if len(p)<1016]
    for i in set(range(len(rows)))-set(valid):rows[i]={'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[],'input_tokens':len(enc[i])}
    if not valid:return rows
    device=next(model.parameters()).device;width=max(len(enc[i])for i in valid)
    ids=torch.zeros((len(valid),width),device=device,dtype=torch.long);mask=torch.zeros_like(ids)
    for j,i in enumerate(valid):ids[j,:len(enc[i])]=torch.tensor(enc[i],device=device);mask[j,:len(enc[i])]=1
    with torch.inference_mode():
        h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
        last=h[torch.arange(len(ids),device=device),mask.sum(1)-1];acts=F.linear(last,action_weight(model)).argmax(-1).tolist()
        c=F.linear(last,correct_weight(model)).float();margins=(c[:,1]-c[:,0]).tolist()
    if forced_action:acts=[ACTIONS.index(forced_action)]*len(valid)
    for act in sorted(set(acts)):
        action=ACTIONS[act];indexes=[i for j,i in enumerate(valid)if acts[j]==act]
        if action in NO_BODY:
            for i in indexes:rows[i]={'action':action,'body':[],'codec_error':None,'generated_token_ids':[ACTION_IDS[act]]}
            continue
        prefixes=[enc[i]+header_ids(tokenizer,action)for i in indexes];length=max(map(len,prefixes))
        values=torch.zeros((len(indexes),length),device=device,dtype=torch.long);attention=torch.zeros_like(values)
        for j,p in enumerate(prefixes):values[j,-len(p):]=torch.tensor(p,device=device);attention[j,-len(p):]=1
        with torch.inference_mode():
            result=model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(511,1024-length),do_sample=False,use_cache=True,
              pad_token_id=0,eos_token_id=END,logits_processor=LogitsProcessorList([BodyGrammar(tokenizer,length,action)]))
        for j,i in enumerate(indexes):
            tail=result[j,length:].tolist();ended=END in tail
            if ended:tail=tail[:tail.index(END)]
            tokens=[ACTION_IDS[act],*tail]
            try:
                if not ended:raise ValueError('incomplete')
                a,b=decode(tokenizer,tokens);error=None
            except ValueError as e:a=None;b=[];error=str(e)
            rows[i]={'action':a,'body':b,'codec_error':error,'generated_token_ids':tokens}
    for j,i in enumerate(valid):rows[i].update(correctness_margin=margins[j],input_tokens=len(enc[i]))
    return rows


def session(g,r,vm,arm,index,scratch=False):
    state=copy.deepcopy(r['state']);s=Session(state['view'],state['pool'],None if scratch else state['body'],vm,arm)
    if not scratch:
        s.runs={int(k):v for k,v in state['runs'].items()};s.case=state['case']
        if(index//4)%2:
            s.revision=1;s.observation='Предыдущая правка выполнена; проверка нового кода продолжается.'
            d=[1,0,0,state['body'][0],0]if r['class']=='correct'else[0,255,255,0,0]
            s.diagnosis={'revision':1,'body':d}
    return s


def summarize(rows):
    good=[r for r in rows if r['initially_correct']];bad=[r for r in rows if not r['initially_correct']]
    return {'total':len(rows),'passed':sum(r['pass']for r in rows),'false_DONE':sum(r['finished']and not r['program_correct']for r in rows),
      'all_DONE':sum(r['finished']for r in rows),'abstained':sum(r['abstained']for r in rows),
      'correct_starts':len(good),'correct_starts_completed':sum(r['pass']for r in good),
      'correct_starts_corrupted':sum(not r['program_correct']for r in good),
      'incorrect_starts':len(bad),'incorrect_starts_repaired':sum(r['pass']for r in bad),
      'final_correct_code':sum(r['program_correct']for r in rows),
      'generation_errors':sum(any(h.get('generation',{}).get('codec_error')for h in r['history'])for r in rows),
      'details':rows,'reference_in_runtime':False,'external_semantic_veto':False}


def panel(model,tokenizer,groups,arm,scratch=False):
    vm=FullVM();items=[(g,g['rows'][3])for g in groups]if scratch else[(g,r)for g in groups for r in g['rows']]
    records=[]
    for at in range(0,len(items),24):
        chunk=items[at:at+24];sessions=[session(g,r,vm,arm,at+j,scratch)for j,(g,r)in enumerate(chunk)]
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];generated=generate(model,tokenizer,prompts)
            for s,p,g in zip(active,prompts,generated):
                if g.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':g});s.exhausted=True;continue
                try:s.apply_action(g['action'],g['body'])
                except (ValueError,ArithmeticError,RuntimeError)as e:
                    s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=g)
        for (g,r),s in zip(chunk,sessions):
            task=g['task'];ok=correct(vm,task,s.body,s.pool);eligible=s.eligibility()[0]
            records.append({'id':r['id']+(':scratch'if scratch else''),'task_id':task['id'],'family':g['family'],'pair_tag':g['pair_tag'],
              'initial_class':'empty'if scratch else r['class'],'initially_correct':not scratch and r['class']=='correct',
              'program_correct':ok,'eligible':eligible,'finished':s.finished,'pass':bool(ok and eligible and s.finished),
              'abstained':s.abstained,'body':s.body,'history':s.history})
    result=summarize(records)
    result['by_family']={f:{k:v for k,v in summarize([r for r in records if r['family']==f]).items()if k!='details'}for f in sorted({r['family']for r in records})}
    return result


def localized(model,tokenizer,groups,arm):
    values=[(g,r)for g in groups for r in g['rows']];details=[]
    for at in range(0,len(values),32):
        chunk=values[at:at+32];prompts=[render({**r['state'],'remaining':12},arm)for g,r in chunk]
        for(g,r),p,v in zip(chunk,prompts,generate(model,tokenizer,prompts,forced_action='diag')):
            expected=diagnosis(r['body'],g['rows'][3]['body'],r['class']);body=v.get('body',[])
            details.append({'id':r['id'],'class':r['class'],'family':r['family'],'expected':expected,
              'generation':v,'prompt':p,'class_match':bool(body and body[0]==expected[0]),'exact_match':body==expected})
    return {'total':len(details),'class_correct':sum(r['class_match']for r in details),'localized_exact':sum(r['exact_match']for r in details),'details':details}


def evaluate(model,tokenizer,split,arm,diagnostic=True):
    groups={name:read(ROOT/(file+'.jsonl'))for name,file in [('known',split),('novel','novel-'+split)]}
    result={n:panel(model,tokenizer,g,arm)for n,g in groups.items()}
    scratch=[g for f in ['binary','memory','mixed','unary']for g in[g for g in groups['known']if g['family']==f][:8]]
    result['scratch']=panel(model,tokenizer,scratch,arm,True)
    if diagnostic:
        result['diagnosis']={n:localized(model,tokenizer,g if split=='fresh'else g[:20],arm)for n,g in groups.items()}
    return result


def key(report):
    values=[report[n]for n in ['known','novel']]
    eligible=all(r['passed']/r['total']>=.8 and r['false_DONE']/r['total']<=.05 and
      r['correct_starts_completed']/r['correct_starts']>=.8 for r in values)
    utilities=[(r['passed']-4*r['false_DONE'])/r['total']for r in values]
    return[eligible,min(utilities),sum(r['passed']for r in values),-sum(r['false_DONE']for r in values)]


def brief(report):
    return{n:{k:v for k,v in r.items()if k not in ['details','by_family']}for n,r in report.items()if n!='diagnosis'}
