"""New natural-language exam with separate authored probes and structured retention."""
from bg_common import ROOT,read,rows
from bg_spec import install
import ay_eval as core
from bc_eval import choose_pools,known_short_probes
from bg_course import Course
from az_runtime import Session
from az_eval import navigation
from bc_self import wrong_program
from bc_pools import goal_layout
from full_isa_vm import FullVM

core.Session=Session;core.mutant=lambda g,vm,kind:(kind,wrong_program(g,vm,kind)[0])

def evaluate(model,tokenizer,split):
    install()
    if split=='closed':assert(ROOT/'preselected.json').exists()
    goals=rows(ROOT/(split+'-clean.jsonl'));vm=FullVM();records=core.primary(model,tokenizer,goals,'spec',vm)
    panels={p:core.primary_metrics([r for r in records if r['panel']==p])for p in ['known','novel','editorial','structured']}
    natural=[r for r in records if r['panel']!='structured']
    result={'split':split,'primary':{'summary':core.primary_metrics(records),'natural':core.primary_metrics(natural),
        'panels':panels,'records':records,'families':{f:core.primary_metrics([r for r in records if r['family']==f])for f in sorted({g['family']for g in goals})}}}
    cohort=core.choose_runtime(goals,32 if split=='development'else 64,261109117);plans={r['id']:r for r in records}
    for gate in ['raw','self']:
        values=core.episodes(model,tokenizer,cohort,'spec',plans,vm,gate);result[gate]={'summary':core.episode_metrics(values),'records':values}
    result['pool_views']={}
    for mode in ['extras','full','distractors']:
        values=core.primary(model,tokenizer,[goal_layout(g,mode,g['id']+':'+mode)for g in choose_pools(goals,48 if split=='development'else 128)],'spec',vm)
        result['pool_views'][mode]={'summary':core.primary_metrics(values),'records':values,'same_tasks_not_independent':True}
    result['navigation']=navigation(model,tokenizer,core.choose_runtime(goals,16 if split=='development'else 32,261109118),'spec',vm)
    result['short_regressions']=known_short_probes(model,tokenizer,vm)
    return result

def key(report,parent):
    panel=report['primary']['panels'];base=parent['primary']['panels']
    rate=lambda p:p['passed']/p['total']
    protected=(all(x['passed']or not b['passed']for x,b in zip(report['short_regressions'],parent['short_regressions']))and
        rate(panel['structured'])>=rate(base['structured'])-.05 and rate(panel['editorial'])>=rate(base['editorial'])-.05)
    natural=report['primary']['natural']
    s=report['self']['summary'];b=parent['self']['summary']
    protected=protected and rate(natural)>=rate(parent['primary']['natural'])-.05
    protected=protected and s['correct_starts_corrupted']<=b['correct_starts_corrupted'] and s['false_DONE']<=b['false_DONE']
    return [bool(protected),s['passed']-2*s['false_DONE']-2*s['correct_starts_corrupted'], -s['false_DONE'],-s['correct_starts_corrupted'],s['passed'],rate(natural)]

def brief(report):return {'natural':report['primary']['natural'],'panels':report['primary']['panels'],
    'raw':report['raw']['summary'],'self':report['self']['summary']}
