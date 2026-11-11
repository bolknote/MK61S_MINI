"""Frozen fresh goals; translation retention and rejection recovery stay separate."""
import copy
import time
from bs_common import ROOT,rows,read
from bl_runtime import Session as CompactSession,render
from bj_runtime import Session as LongSession
from bl_prompt import LIMIT
from bl_spec import install
from bl_vm import CachedVM
from bk_independent_generate import generate as independent
from aq_protocol import prompt_ids
from bs_resources import duty
import bj_eval as base


def cohort(goals,n):
    if len(goals)<=n:return goals
    result=[];families=sorted({g['family']for g in goals})
    for family in families:result.extend([g for g in goals if g['family']==family][:n//len(families)])
    ids={g['id']for g in result}
    for g in goals:
        if len(result)>=n:break
        if g['id']not in ids:result.append(g);ids.add(g['id'])
    return result


def evaluate(model,tokenizer,split,profile='compact',shared_policy=None):
    install()
    if split=='closed':assert(ROOT/'preselected.json').exists()
    goals=rows(ROOT/(split+'.jsonl'));vm=CachedVM();budgets=[];policy=shared_policy or read(ROOT/'policy.json')
    old=(base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant)
    def generate(m,t,prompts,forced_action=None):
        out=[]
        for p in prompts:
            start=time.monotonic();n=len(prompt_ids(t,p));budgets.append(n)
            if profile=='compact'and n>LIMIT:out.append({'action':None,'body':[],'codec_error':'reserved_context_exceeded','generated_token_ids':[],'input_tokens':n})
            else:out.extend(independent(m,t,[p],forced_action))
            duty(start,policy)
        return out
    try:
        CompactSession.tokenizer=tokenizer;base.Session=CompactSession if profile=='compact'else LongSession
        base.generate=generate;base.core.generate=generate
        if profile=='compact':base.core.render=lambda state,arm:render(state,tokenizer)[0]
        base.core.mutant=lambda g,vm,kind:(g['error_kind'],g['bad_body'])
        primary=base.core.primary(model,tokenizer,goals,'spec',vm);plans={r['id']:r for r in primary}
        selected=cohort(goals,48 if split=='development'else 256)
        own=base.episodes(model,tokenizer,selected,plans,vm,'self')
        stress=cohort([g for g in goals if g['family']=='composition'],16 if split=='development'else 32)
        wrong=base.episodes(model,tokenizer,stress,{g['id']:{'declared_spec':g['bad_spec']}for g in stress},vm,'self')
        if profile=='compact':
            class Rejected(CompactSession):
                def __init__(self,g,body,vm,arm,declared,gate):
                    super().__init__(g,body,vm,arm,g['spec'],gate)
                    if body==g['reference_body']:self.runs.pop(1-self.case,None)
                    result=self.apply_action('done',[]);assert result=='done_rejected'
                    self.history[-1]['harness_forced']='evaluation_setup'
                def apply_action(self,action,body):
                    value=super().apply_action(action,body)
                    if len(self.history)>=12 and not self.finished:self.exhausted=True
                    return value
                def apply_replan(self,body):
                    value=super().apply_replan(body)
                    if len(self.history)>=12 and not self.finished:self.exhausted=True
                    return value
            base.Session=Rejected
            recovery=base.episodes(model,tokenizer,cohort(goals,32 if split=='development'else 64),plans,vm,'self')
            for r in recovery:r['DONE_claims']-=1;r['false_DONE_claims']-=int(not r['initially_correct'])
        else:recovery=[]
        result={'split':split,'profile':profile,'primary':{'summary':base.core.primary_metrics(primary),
           'by_family':{f:base.core.primary_metrics([r for r in primary if r['family']==f])for f in sorted({r['family']for r in primary})},'records':primary},
           'own':{'summary':base.metrics(own),'records':own},'wrong':{'summary':base.metrics(wrong),'records':wrong},
           'recovery':{'summary':base.metrics(recovery),'records':recovery}if recovery else None,
           'budget':{'calls':len(budgets),'maximum':max(budgets),'reserved_context_failures':sum(n>LIMIT for n in budgets)if profile=='compact'else None}}
        if split=='development':
            values=base.core.primary(model,tokenizer,rows(ROOT/'retention.jsonl'),'spec',vm)
            result['retention']={'summary':base.core.primary_metrics(values),'records':values}
        result['budget']={'calls':len(budgets),'maximum':max(budgets),'reserved_context_failures':sum(n>LIMIT for n in budgets)if profile=='compact'else None}
        return result
    finally:base.Session,base.generate,base.core.generate,base.core.render,base.core.mutant=old


def key(report,parent):
    a=report['own']['summary'];b=parent['own']['summary'];w=report['wrong']['summary'];v=parent['wrong']['summary']
    keep={r['id']for r in parent['retention']['records']if r['program_correct']}
    lost=sum(r['id']in keep and not r['program_correct']for r in report['retention']['records'])
    checks={'lost_parent_correct_translation':lost,'translation_retained':lost<=2,
        'false_DONE':a['false_DONE']<=b['false_DONE'],'wrong_SPEC_false_DONE':w['false_DONE']<=v['false_DONE'],
        'corruption':a['correct_starts_corrupted']<=b['correct_starts_corrupted'],
        'correct_starts_completed':a['correct_starts_completed']>=b['correct_starts_completed'],
        'repairs':a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
        'false_claim_episodes':a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims']}
    if report.get('recovery')and parent.get('recovery'):
        a1=report['recovery']['summary'];b1=parent['recovery']['summary']
        checks.update(rejected_correct_starts=a1['correct_starts_completed']>=b1['correct_starts_completed'],
                      rejected_repairs=a1['wrong_starts_repaired']>=b1['wrong_starts_repaired'],
                      rejected_false_DONE=a1['false_DONE']<=b1['false_DONE'])
    ok=all(x for k,x in checks.items()if k!='lost_parent_correct_translation')
    return [ok,a['wrong_starts_repaired'],a['passed'],-a['false_DONE'],-w['false_DONE'],-lost,-a['episodes_with_false_DONE_claims'],report['primary']['summary']['passed']],checks


def brief(r):return {'primary':r['primary']['summary'],'by_family':r['primary']['by_family'],**{k:r[k]['summary']if r[k]else None for k in ['own','wrong','recovery']},'retention':r.get('retention',{}).get('summary')}
