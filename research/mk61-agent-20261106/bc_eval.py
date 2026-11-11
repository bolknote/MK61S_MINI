"""Fresh Q4 exam; matched table permutations and bounded actor episodes."""
import collections
import random
from bc_common import ROOT,read,rows
from bc_pools import goal_layout
from bc_lessons import wrong_program
from az_runtime import Session
from az_eval import navigation,regression
import ay_eval as core
from full_isa_vm import FullVM
from aq_eval import generate
from az_runtime import render,goal_state
from az_teacher import pool_for
from ay_codec import to_program
from ar_spec import verify
from bc_self import rejected_session

core.Session=Session
core.mutant=lambda g,vm,kind:(kind,wrong_program(g,vm,kind)[0])

def controlled_checks(model,tokenizer,groups,vm):
    jobs=[];records=[]
    for g in groups:
        for kind in ['valid_feedback','wrong_hypothesis']:
            try:s=rejected_session(g,vm,kind)
            except (ValueError,ArithmeticError):continue
            if not s.finished:jobs.append((g,kind,s))
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24]
        for turn in range(6):
            active=[(g,k,s)for g,k,s in chunk if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for g,k,s in active];values=generate(model,tokenizer,prompts)
            for(g,k,s),p,v in zip(active,prompts,values):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as e:
                    s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        for g,k,s in chunk:
            correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
            records.append({'id':g['id']+':'+k,'task_id':g['id'],'kind':k,'finished':s.finished,'abstained':s.abstained,
                'program_correct':correct,'false_DONE':bool(s.finished and not correct),
                'success':bool(s.finished and correct and s.eligibility()[0]),
                'safe_exit':bool(k=='wrong_hypothesis'and correct and s.abstained and not s.finished),'history':s.history})
    return {'total':len(records),'valid_feedback_total':sum(r['kind']=='valid_feedback'for r in records),
       'valid_feedback_success':sum(r['kind']=='valid_feedback'and r['success']for r in records),
       'wrong_hypothesis_total':sum(r['kind']=='wrong_hypothesis'for r in records),
       'wrong_hypothesis_false_DONE':sum(r['kind']=='wrong_hypothesis'and r['false_DONE']for r in records),
       'safe_conflict_exits':sum(r['safe_exit']for r in records),'records':records}


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
    rng=random.Random(26110867);result=[]
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
    plans={r['id']:r for r in records};cohort=core.choose_runtime(groups,64 if split=='development'else 128,26110868)
    for gate in ['raw','self']:
        data=core.episodes(model,tokenizer,cohort,'spec',plans,vm,gate)
        result[gate]={'summary':core.episode_metrics(data),'records':data}
    permuted=core.choose_runtime(full_goals,16 if split=='development'else 32,26110869)
    data=core.episodes(model,tokenizer,permuted,'spec',{r['id']:r for r in pool_records['full']},vm,'raw')
    result['permuted_raw']={'summary':core.episode_metrics(data),'records':data}
    nav_goals=core.choose_runtime(groups,16 if split=='development'else 32,26110870)
    nav=navigation(model,tokenizer,nav_goals,'spec',vm);result['navigation']={'summary':{k:v for k,v in nav.items()if k!='records'},'records':nav['records']}
    result['regression']=regression(model,tokenizer,'spec',vm)
    result['short_regressions']=known_short_probes(model,tokenizer,vm)
    controlled=controlled_checks(model,tokenizer,core.choose_runtime(groups,16 if split=='development'else 32,26110871),vm)
    result['controlled_checks']={'summary':{k:v for k,v in controlled.items()if k!='records'},'records':controlled['records']}
    return result


def key(report,parent):
    p,bp=report['primary']['summary'],parent['primary']['summary']
    raw,br=report['raw']['summary'],parent['raw']['summary']
    own,bo=report['self']['summary'],parent['self']['summary']
    rates={k:v['summary']['passed']/v['summary']['total']for k,v in report['pool_views'].items()}
    base_rates={k:v['summary']['passed']/v['summary']['total']for k,v in parent['pool_views'].items()}
    nav,bnav=report['navigation']['summary'],parent['navigation']['summary']
    conflict=report['controlled_checks']['summary'];base_conflict=parent['controlled_checks']['summary']
    protected=(p['passed']/p['total']>=bp['passed']/bp['total']-.03 and
       raw['passed']/raw['total']>=br['passed']/br['total']-.03 and
       own['passed']/own['total']>=bo['passed']/bo['total']-.03 and
       min(rates.values())>=min(base_rates.values())-.05 and nav['cycle_pass']>=bnav['cycle_pass']-1 and
       conflict['valid_feedback_success']>=base_conflict['valid_feedback_success']-1 and
       all(n['passed']or not b['passed']for n,b in zip(report['short_regressions'],parent['short_regressions'])))
    improved=own['false_DONE']<bo['false_DONE']and conflict['wrong_hypothesis_false_DONE']<=base_conflict['wrong_hypothesis_false_DONE']
    return [bool(protected),bool(improved),-own['false_DONE'],own['passed'],conflict['safe_conflict_exits'],raw['passed'],p['passed'],min(rates.values())]


def brief(r):
    return {k:v['summary']for k,v in r.items()if isinstance(v,dict)and'summary'in v}|{'pool_views':{k:v['summary']for k,v in r['pool_views'].items()}}
