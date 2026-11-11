"""Same fresh Q4 exam for parent, LoRA and all-weight continuation."""
import collections
import random
from be_common import ROOT,rows,read
import ay_eval as core
from bc_eval import choose_pools,known_short_probes
from bc_self import wrong_program
from bc_pools import goal_layout
from az_runtime import Session
from az_eval import navigation
from full_isa_vm import FullVM

core.Session=Session
core.mutant=lambda g,vm,kind:(kind,wrong_program(g,vm,kind)[0])

def evaluate(model,tokenizer,split):
    if split=='closed':assert(ROOT/'preselected.json').exists()
    groups=rows(ROOT/(split+'-clean.jsonl'));vm=FullVM();values=core.primary(model,tokenizer,groups,'spec',vm)
    result={'split':split,'primary':{'summary':core.primary_metrics(values),'records':values,
        'panels':{p:core.primary_metrics([r for r in values if r['panel']==p])for p in ['known','novel','editorial']},
        'families':{f:core.primary_metrics([r for r in values if r['family']==f])for f in sorted({g['family']for g in groups})},
        'styles':{f:core.primary_metrics([r for r,g in zip(values,groups)if g['style']==f])for f in sorted({g['style']for g in groups})}}}
    cohort=core.choose_runtime(groups,32 if split=='development'else 64,26110896)
    plans={r['id']:r for r in values}
    for gate in ['raw','self']:
        data=core.episodes(model,tokenizer,cohort,'spec',plans,vm,gate)
        result[gate]={'summary':core.episode_metrics(data),'records':data}
    result['pool_views']={}
    for mode in ['extras','full','distractors']:
        changed=[goal_layout(g,mode,g['id']+':'+mode)for g in choose_pools(groups,48 if split=='development'else 128)]
        data=core.primary(model,tokenizer,changed,'spec',vm)
        result['pool_views'][mode]={'summary':core.primary_metrics(data),'records':data,'same_tasks_not_independent_examples':True}
    nav=navigation(model,tokenizer,core.choose_runtime(groups,16 if split=='development'else 32,26110897),'spec',vm)
    result['navigation']=nav;result['short_regressions']=known_short_probes(model,tokenizer,vm)
    return result

def key(report):
    panels=report['primary']['panels'];core_total=sum(panels[p]['total']for p in ['known','novel'])
    a=sum(panels[p]['passed']for p in ['known','novel'])/core_total
    b=panels['editorial']['passed']/panels['editorial']['total']
    return [all(r['passed']for r in report['short_regressions']),(a+b)/2,min(a,b),report['primary']['summary']['passed'],
        -report['primary']['summary']['codec_errors'],report['raw']['summary']['passed'],-report['self']['summary']['false_DONE']]

def brief(report):
    return {'primary':report['primary']['summary'],'panels':report['primary']['panels'],
        'raw':report['raw']['summary'],'self':report['self']['summary'],'key':key(report)}
