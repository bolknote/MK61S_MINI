"""New closed exam, explicit navigation probes and the known sin22 regression."""
import collections
import copy
from az_common import ROOT,rows
from az_runtime import Session,goal_state,render
from az_teacher import pool_for,augment_pool
from az_lessons import mutant
from ay_codec import encode,to_program,compile_spec
import ay_eval as base
from aq_eval import generate
from full_isa_vm import FullVM
from ar_spec import verify

base.Session=Session
base.mutant=mutant
primary_metrics=base.primary_metrics
episode_metrics=base.episode_metrics


def navigation(model,tokenizer,groups,arm,vm):
    jobs=[(g,case)for g in groups for case in [0,1]];records=[]
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24];sessions=[]
        for g,case in chunk:
            s=Session(g,g['reference_body'],vm,arm,start_case=case)
            body=g['reference_body']if arm=='hex'else g['spec_body']
            s.apply_action('write',body);assert set(s.runs)=={case}
            sessions.append(s)
        for turn in range(5):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];generated=generate(model,tokenizer,prompts)
            for s,p,v in zip(active,prompts,generated):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as e:
                    s.observation='ERROR '+str(e);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        for(g,case),s in zip(chunk,sessions):
            generated=[h['generation']for h in s.history if'generation'in h];first=generated[0]if generated else{}
            correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
            records.append({'id':g['id']+f':need-{1-case:02X}','task_id':g['id'],'needed_case':1-case,
              'next_step_correct':first.get('action')=='run'and first.get('body')==[1-case],
              'finished':s.finished,'eligible':s.eligibility()[0],'program_correct':correct,
              'cycle_pass':bool(s.finished and s.eligibility()[0]and correct),'history':s.history})
    return {'total':len(records),'next_step_correct':sum(r['next_step_correct']for r in records),
            'cycle_pass':sum(r['cycle_pass']for r in records),
            'by_case':{str(i):{'total':sum(r['needed_case']==i for r in records),
                      'next_step_correct':sum(r['needed_case']==i and r['next_step_correct']for r in records),
                      'cycle_pass':sum(r['needed_case']==i and r['cycle_pass']for r in records)}for i in [0,1]},'records':records}


def regression(model,tokenizer,arm,vm):
    text='Вычисли синус 22 градусов. Результат оставь в X; остановись.'
    g={'id':'known-sin22','task':text,'pool':pool_for(text),'spec':{'X':['sin',{'constant':'22'}],'writes':{},'angle':'DEG'},
       'public_inputs':[],'checker_inputs':[],'audit_inputs':[{}]}
    p=render(goal_state(g),arm);v=generate(model,tokenizer,[p],forced_action='write')[0];program=[];error=v.get('codec_error')
    if not error:
        try:program,_=to_program(v['body'],g['pool'],'DEG',arm)
        except (ValueError,ArithmeticError,RuntimeError)as e:error=str(e)
    check=verify(vm,program,g['pool'],g['spec'],[{}])
    return {'passed':check['status']=='TESTED','generation':v,'program':program,'audit':check,'error':error,
            'prompt':p,'training_regression_not_closed_exam':True}


def evaluate(model,tokenizer,split,arm):
    if split=='closed':assert(ROOT/'preselected.json').exists()
    groups=rows(ROOT/(split+'-clean.jsonl'));vm=FullVM();records=base.primary(model,tokenizer,groups,arm,vm)
    index={g['id']:g for g in groups}
    for r in records:
        g=index[r['id']];r.update(style=g.get('style'),pool_layout=g.get('pool_layout'),curriculum=g.get('curriculum'))
    result={'arm':arm,'split':split,'primary':{'summary':primary_metrics(records),'records':records,
        'panels':{p:primary_metrics([r for r in records if r['panel']==p])for p in ['known','novel']},
        'families':{f:primary_metrics([r for r in records if r['family']==f])for f in sorted({g['family']for g in groups})}}}
    cohort=base.choose_runtime(groups,32 if split=='development'else 128,26110826);plans={r['id']:r for r in records}
    for gate in (['raw']if split=='development'else['raw','self']):
        data=base.episodes(model,tokenizer,cohort,arm,plans,vm,gate)
        result[gate]={'summary':episode_metrics(data),'records':data,
                     'panels':{p:episode_metrics([r for r in data if r['panel']==p])for p in ['known','novel']}}
    nav_groups=base.choose_runtime(groups,16 if split=='development'else 32,26110828)
    nav=navigation(model,tokenizer,nav_groups,arm,vm);result['navigation']={'summary':{k:v for k,v in nav.items()if k!='records'},'records':nav['records']}
    result['regression']=regression(model,tokenizer,arm,vm)
    if split=='closed':
        stress=[]
        for g in base.choose_runtime(groups,64,26110829):
            if g['family']not in ['constant','numeric']:continue
            item=copy.deepcopy(g);item['pool']=augment_pool(pool_for(g['task']),g['id']+':pool-stress')
            item['reference_body']=compile_spec(g['spec'],item['pool']);item['spec_body']=encode(g['spec'],item['pool']);stress.append(item)
        values=base.primary(model,tokenizer,stress,arm,vm)
        result['pool_stress']={'summary':primary_metrics(values),'records':values,'same_ASTs_not_independent_tasks':True}
    return result


def key(report):
    rates=[v['passed']/v['total']for v in report['primary']['panels'].values()]
    rates += [v['next_step_correct']/v['total']for v in report['navigation']['summary']['by_case'].values()]
    raw=report['raw']['summary'];unchecked=sum(r['finished']and r['program_correct']and not r['eligible']for r in report['raw']['records'])
    return [bool(report['regression']['passed']),min(rates),report['primary']['summary']['passed'],raw['passed']-raw['false_DONE']-unchecked]


def brief(report):
    return {name:value['summary']for name,value in report.items()if isinstance(value,dict)and'summary'in value}
