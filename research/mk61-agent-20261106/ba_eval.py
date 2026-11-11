"""Fresh Q4 exam; matched table permutations and bounded actor episodes."""
import collections
import random
from ba_common import ROOT,read,rows
from ba_pools import goal_layout
from ba_lessons import wrong_program
from az_runtime import Session
from az_eval import navigation,regression
import ay_eval as core
from full_isa_vm import FullVM
from aq_eval import generate
from az_runtime import render,goal_state
from az_teacher import pool_for
from ay_codec import to_program
from ar_spec import verify

core.Session=Session
core.mutant=lambda g,vm,kind:(kind,wrong_program(g,vm,kind)[0])


def known_short_probes(model,tokenizer,vm):
    records=[]
    for task,value in [('Синус 22','22'),('Синус -22 градусов','-22'),('Вычисли синус 29.5 градусов.','29.5')]:
        goal={'id':'known:'+task,'task':task,'pool':pool_for(task),'public_inputs':[],
           'spec':{'X':['sin',{'constant':value}],'writes':{},'angle':'DEG'}}
        prompt=render(goal_state(goal),'spec');v=generate(model,tokenizer,[prompt],forced_action='write')[0];program=[]
        if not v.get('codec_error'):
            try:program,_=to_program(v['body'],goal['pool'],'DEG','spec')
            except (ValueError,ArithmeticError):pass
        records.append({'task':task,'passed':verify(vm,program,goal['pool'],goal['spec'],[{}])['status']=='TESTED',
            'generation':v,'prompt':prompt,'program':program,'known_not_new_exam':True})
    return records


def choose_pools(goals,n):
    rng=random.Random(26110847);result=[]
    for panel in ['known','novel']:
        for family in ['constant','numeric']:
            values=[g for g in goals if g['panel']==panel and g['family']==family]
            result+=rng.sample(values,min(n//4,len(values)))
    return result


def evaluate(model,tokenizer,split):
    if split=='closed':assert(ROOT/'preselected.json').exists()
    groups=rows(ROOT/(split+'-clean.jsonl'));vm=FullVM();records=core.primary(model,tokenizer,groups,'spec',vm)
    result={'arm':'spec','split':split,'primary':{'summary':core.primary_metrics(records),'records':records,
        'families':{f:core.primary_metrics([r for r in records if r['family']==f])for f in sorted({g['family']for g in groups})},
        'panels':{p:core.primary_metrics([r for r in records if r['panel']==p])for p in ['known','novel']}}}
    pool_goals=choose_pools(groups,48 if split=='development'else 128);pool_records={};full_goals=[]
    result['pool_views']={}
    for mode in ['extras','full','distractors']:
        changed=[goal_layout(g,mode,g['id']+':exam:'+mode)for g in pool_goals]
        data=core.primary(model,tokenizer,changed,'spec',vm);pool_records[mode]=data
        result['pool_views'][mode]={'summary':core.primary_metrics(data),'records':data,
            'same_ASTs_as_primary_not_independent_tests':True,
            'same_value_set_as_primary':mode!='distractors','actually_changed_tables':sum(a['pool']!=b['pool']for a,b in zip(pool_goals,changed))}
        if mode=='full':full_goals=changed
    plans={r['id']:r for r in records};cohort=core.choose_runtime(groups,32 if split=='development'else 128,26110848)
    for gate in ['raw']if split=='development'else['raw','self']:
        data=core.episodes(model,tokenizer,cohort,'spec',plans,vm,gate)
        result[gate]={'summary':core.episode_metrics(data),'records':data}
    permuted=core.choose_runtime(full_goals,16 if split=='development'else 32,26110849)
    data=core.episodes(model,tokenizer,permuted,'spec',{r['id']:r for r in pool_records['full']},vm,'raw')
    result['permuted_raw']={'summary':core.episode_metrics(data),'records':data}
    nav_goals=core.choose_runtime(groups,16 if split=='development'else 32,26110850)
    nav=navigation(model,tokenizer,nav_goals,'spec',vm);result['navigation']={'summary':{k:v for k,v in nav.items()if k!='records'},'records':nav['records']}
    result['regression']=regression(model,tokenizer,'spec',vm)
    result['short_regressions']=known_short_probes(model,tokenizer,vm)
    return result


def key(report,parent):
    p=report['primary']['summary'];bp=parent['primary']['summary'];r=report['raw']['summary'];br=parent['raw']['summary']
    rates={k:v['summary']['passed']/v['summary']['total']for k,v in report['pool_views'].items()}
    base_rates={k:v['summary']['passed']/v['summary']['total']for k,v in parent['pool_views'].items()}
    nav=report['navigation']['summary'];bn=parent['navigation']['summary']
    unchecked=sum(x['finished']and x['program_correct']and not x['eligible']for x in report['raw']['records'])
    protected=(p['passed']/p['total']>=bp['passed']/bp['total']-.03 and
        r['passed']/r['total']>=br['passed']/br['total']-.03 and nav['cycle_pass']>=bn['cycle_pass']-1 and
        (report['regression']['passed']or not parent['regression']['passed'])and unchecked==0)
    protected=protected and all(n['passed']or not b['passed']for n,b in zip(report['short_regressions'],parent['short_regressions']))
    improved=(r['false_DONE']<=br['false_DONE']and min(rates.values())>=min(base_rates.values())+.1)
    return [bool(protected),bool(improved),-r['false_DONE']-unchecked,min(rates.values()),r['passed'],p['passed']]


def brief(r):
    return {k:v['summary']for k,v in r.items()if isinstance(v,dict)and'summary'in v}|{'pool_views':{k:v['summary']for k,v in r['pool_views'].items()}}
