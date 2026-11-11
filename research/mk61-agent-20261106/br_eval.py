"""Separate memorized states, free tool cycles, and held-out generalization."""
import collections
import torch
import torch.nn.functional as F
from br_common import ROOT,ACTIONS,ACTION_IDS,body_ids,read,rows
from bp_course import encoded
from aq_course import pad
from bl_runtime import Session,render
from bl_prompt import LIMIT
from bl_vm import CachedVM
from bl_spec import install
from bk_independent_generate import generate as independent
from aq_protocol import prompt_ids
import bj_eval as base


@torch.inference_mode()
def states(model,tokenizer):
    """Teacher forcing measures fitting only; free cycles are reported separately."""
    values=rows(ROOT/'lessons.jsonl');details=[];device=next(model.parameters()).device
    head=torch.tensor(body_ids(tokenizer),device=device)
    weight=model.get_input_embeddings().weight
    for at in range(0,len(values),8):
        chunk=values[at:at+8];batch=[encoded(tokenizer,r)for r in chunk]
        ids,mask,labels,positions,actions=pad(batch,device)
        hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
        predicted=F.linear(hidden[torch.arange(len(ids),device=device),positions],weight[ACTION_IDS]).argmax(-1)
        for j,r in enumerate(chunk):
            valid=labels[j,1:]!=-100;target=labels[j,1:][valid]
            predictions=head[F.linear(hidden[j,:-1][valid],weight[head]).argmax(-1)]if len(target)else target
            details.append({'id':r['id'],'origin':r['origin'],'action_eligible':r['origin']not in ['goal','review_fix','review_keep'],
                  'expected_action':r['action'],'predicted_action':ACTIONS[int(predicted[j])],
                  'action_correct':bool(predicted[j]==actions[j]),'body_tokens':len(target),
                  'body_correct_tokens':int((predictions==target).sum()),'body_exact':bool(torch.equal(predictions,target))})
    def summary(items):
        act=[r for r in items if r['action_eligible']];body=[r for r in items if r['body_tokens']]
        return {'rows':len(items),'action_total':len(act),'action_correct':sum(r['action_correct']for r in act),
                'body_total':len(body),'body_exact':sum(r['body_exact']for r in body),
                'body_tokens':sum(r['body_tokens']for r in body),'body_correct_tokens':sum(r['body_correct_tokens']for r in body)}
    return {'summary':summary(details),'by_origin':{o:summary([r for r in details if r['origin']==o])for o in sorted({r['origin']for r in details})},
            'records':details,'teacher_forcing_only':True}


def evaluate(model,tokenizer,panel,modes=('own','gold','wrong')):
    install()
    if panel!='train':assert(ROOT/'preselected.json').exists(),'No held-out generations before selection'
    goals=rows(ROOT/(panel+'.jsonl'));vm=CachedVM();budgets=[]
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        result=[]
        for prompt in prompts:
            n=len(prompt_ids(t,prompt));budgets.append(n)
            if n>LIMIT:result.append({'action':None,'body':[],'codec_error':'reserved_context_exceeded','generated_token_ids':[],'input_tokens':n})
            else:result.extend(independent(m,t,[prompt],forced_action))
        return result
    try:
        Session.tokenizer=tokenizer;base.Session=Session;base.generate=generate;base.core.generate=generate
        base.core.render=lambda state,arm:render(state,tokenizer)[0]
        base.core.mutant=lambda g,vm,kind:('fixed_valid_wrong',g['bad_body'])
        primary=base.core.primary(model,tokenizer,goals,'spec',vm)
        result={'panel':panel,'primary':{'summary':base.core.primary_metrics(primary),'records':primary},'modes':{}}
        for mode in modes:
            plans={r['id']:r for r in primary}if mode=='own'else{g['id']:{'declared_spec':g['spec'if mode=='gold'else'bad_spec']}for g in goals}
            values=base.episodes(model,tokenizer,goals,plans,vm,'self')
            result['modes'][mode]={'summary':base.metrics(values),'records':values,'oracle_initial_SPEC':mode!='own'}
        result['budget']={'calls':len(budgets),'maximum':max(budgets),'reserved_context_failures':sum(n>LIMIT for n in budgets)}
        result['ROM_cache']={'hits':vm.hits,'misses':vm.misses}
        return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def selection(report,state):
    s=state['summary'];p=report['primary']['summary'];m=report['modes']
    rate=lambda n,d:n/d if d else 0.
    success=sum(m[x]['summary']['passed']for x in ['gold','wrong'])
    total=sum(m[x]['summary']['total']for x in ['gold','wrong'])
    false=sum(m[x]['summary']['false_DONE']for x in m)
    corruption=sum(m[x]['summary']['correct_starts_corrupted']for x in m)
    fit=rate(s['action_correct'],s['action_total'])>=.99 and rate(s['body_exact'],s['body_total'])>=.98 and rate(success,total)>=.98 and false==0 and corruption==0
    key=[fit,success,-false,-corruption,s['action_correct'],s['body_exact'],m['own']['summary']['passed'],p['passed']]
    return key,{'training_states_and_cycles_fit':fit,'action_accuracy':rate(s['action_correct'],s['action_total']),
                'body_sequence_accuracy_teacher_forced':rate(s['body_exact'],s['body_total']),
                'diagnostic_gold_wrong_cycles':success,'diagnostic_cycles_total':total,
                'own_SPEC_cycles':m['own']['summary']['passed'],'false_DONE':false,'corruption':corruption}


def brief(report):
    return {'primary':report['primary']['summary'],'cycles':{k:v['summary']for k,v in report['modes'].items()},'budget':report['budget']}
