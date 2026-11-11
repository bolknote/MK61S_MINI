"""Fresh held-out intents and identical typed tool loops, with independent budgets."""
import collections
from bl_common import ROOT, rows
from bl_spec import install
from bl_vm import CachedVM
from bl_runtime import Session, render
from bl_prompt import LIMIT
from bj_runtime import Session as LongSession
from bk_independent_generate import generate as independent
from aq_protocol import prompt_ids
import bj_eval as base


def evaluate(model, tokenizer, split, profile='compact'):
    install()
    if split == 'closed': assert (ROOT / 'preselected.json').exists()
    goals=rows(ROOT/(split+'-clean.jsonl')); vm=CachedVM(); budgets=[]
    old=(base.Session,base.generate,base.core.generate,base.core.render)
    def generate(m,t,prompts,forced_action=None):
        result=[]
        for p in prompts:
            n=len(prompt_ids(t,p));budgets.append(n)
            if profile=='compact' and n>LIMIT:
                result.append({'action':None,'body':[],'codec_error':'reserved_context_exceeded','generated_token_ids':[],'input_tokens':n})
            else: result.extend(independent(m,t,[p],forced_action))
        return result
    try:
        Session.tokenizer=tokenizer
        base.Session=Session if profile=='compact' else LongSession
        base.generate=generate;base.core.generate=generate
        if profile=='compact': base.core.render=lambda state,arm:render(state,tokenizer)[0]
        primary=base.core.primary(model,tokenizer,goals,'spec',vm)
        panels={p:base.core.primary_metrics([r for r in primary if r['panel']==p])for p in ['known','novel','editorial','structured']}
        cohort=base.core.choose_runtime(goals,96 if split=='development'else 256,261112117)
        records=base.episodes(model,tokenizer,cohort,{r['id']:r for r in primary},vm,'self')
        summary=base.metrics(records)
        summary['reserved_context_failures']=sum(any(h.get('generation',{}).get('codec_error')=='reserved_context_exceeded'for h in r['history'])for r in records)
        return {'split':split,'profile':profile,'primary':{'summary':base.core.primary_metrics(primary),'natural':base.core.primary_metrics([r for r in primary if r['panel']!='structured']), 'panels':panels,'records':primary},
                'self':{'summary':summary,'records':records},'budget':{'calls':len(budgets),'maximum':max(budgets),'mean':sum(budgets)/len(budgets)},
                'ROM_cache':{'hits':vm.hits,'misses':vm.misses}}
    finally: base.Session,base.generate,base.core.generate,base.core.render=old


def key(report, parent):
    a=report['self']['summary']; b=parent['self']['summary']
    checks={'accepted_false_DONE':a['false_DONE']<=b['false_DONE'],
            'corruption':a['correct_starts_corrupted']<=b['correct_starts_corrupted'],
            'repairs':a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
            'completion':a['passed']>=b['passed'],
            'false_claim_episodes':a['episodes_with_false_DONE_claims']<=b['episodes_with_false_DONE_claims']}
    rate=lambda x:x['passed']/x['total']
    checks['natural']=rate(report['primary']['natural'])>=rate(parent['primary']['natural'])-.03
    for p in ['editorial','structured']:checks[p]=rate(report['primary']['panels'][p])>=rate(parent['primary']['panels'][p])-.05
    score=[all(checks.values()),a['wrong_starts_repaired'],a['passed'],-a['false_DONE'],-a['correct_starts_corrupted'],-a['episodes_with_false_DONE_claims'],rate(report['primary']['natural'])]
    return score,checks


def brief(report):
    return {'profile':report['profile'],'natural':report['primary']['natural'],'panels':report['primary']['panels'],'self':report['self']['summary'],'budget':report['budget']}
