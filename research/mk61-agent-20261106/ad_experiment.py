"""Local, sealed simulation of candidate ranking and task-independent critic feedback."""
import argparse
import collections
import itertools
import json
import time
from ad_common import ROOT,PREVIOUS,MODEL,PRIOR_ROOT,HERE,read,write,save,sha
from ad_features import Critic
from ad_inference import Bank
from ac_teacher import make_session
from ac_runtime import Session
from ac_eval import stats
from ha_protocol import assemble,constants
from full_isa_vm import FullVM,check_task


def public_task(t):
    return {k:t[k]for k in ['id','task','angle','constants','max_commands','max_frames']if k in t}|{
      'public_tests':[{'segments':[{'inputs':dict(s['inputs'])}for s in c['segments']]}for c in t['public_tests']]}


def grade(vm,task,body):
    try:return bool(body and check_task(vm,assemble(body,task.get('constants')or constants(task['task']),'asm'),task)['pass'])
    except (ValueError,RuntimeError,ArithmeticError):return False


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def rank(rows,critic,pool,config):
    values=[]
    for i,row in enumerate(rows):
        if row.get('codec_error')or row.get('action')!='write':continue
        feature=critic.inspect(tuple(row['body']),tuple(pool))
        if not feature['valid']:continue
        value=row['mean_body_logprob']+critic.score(feature,config)
        values.append((value,-i,i,feature))
    if not values:return 0,None
    value,_,index,feature=max(values)
    return index,feature


def initial_panel(bank,split):
    target=ROOT/(split+'-candidate-panel.json')
    if target.exists():return json.loads(target.read_text())
    vm=FullVM();tasks=read(ROOT/(split+'.jsonl'));lookup={t['id']:t for t in tasks};seeds=read(ROOT/(split+'-seeds.jsonl'))
    critics={p:Critic(p)for p in ['verified_training','combined']};details=[];started=time.monotonic()
    for at in range(0,len(seeds),16):
        items=seeds[at:at+16];sessions=[make_session(public_task(lookup[i['task_id']]),i,vm)for i in items]
        prompts=[s.request()for s in sessions];actions=bank.actions(prompts);candidates=bank.candidates(prompts,actions)
        for seed,s,g,rows in zip(items,sessions,actions,candidates):
            t=lookup[seed['task_id']];pool=s.pool;values=[]
            for row in rows:
                feature={p:c.inspect(tuple(row['body']),tuple(pool))if not row.get('codec_error')else{'valid':False}for p,c in critics.items()}
                values.append({'generation':row,'features':feature,'correct_offline':grade(vm,t,row.get('body'))if not row.get('codec_error')else False})
            details.append({'id':t['id'],'level':t['level'],'initially_correct':seed['intentionally_correct'],
                  'policy_action':g.get('action'),'prompt':s.request(),'pool':pool,'candidates':values})
        status('candidate_panel',split=split,completed=len(details),total=len(seeds),seconds=time.monotonic()-started)
        print(json.dumps({'panel':split,'states':len(details),'total':len(seeds),'seconds':time.monotonic()-started}),flush=True)
    result={'split':split,'details':details,'total':len(details),'actual_inference':bank.actual,'seconds':time.monotonic()-started}
    write(target,result);return result


def select(panel):
    if(ROOT/'selection.json').exists():return json.loads((ROOT/'selection.json').read_text())
    configs=[]
    for prior,weight,repeat,unreachable in itertools.product(['verified_training','combined'],[0.,.25,.5,1.],[0.,1.],[0.,1.]):
        config={'prior':prior,'weight':weight,'repeat':repeat,'unreachable':unreachable};passed=0;changes=0
        for row in panel['details']:
            scores=[]
            for i,c in enumerate(row['candidates']):
                f=c['features'][prior]
                if not f['valid']:continue
                score=c['generation']['mean_body_logprob']+weight*f['log_prior']-repeat*f['repeat_fraction']-unreachable*f['unreachable_fraction']
                scores.append((score,-i,i))
            index=max(scores)[2]if scores else 0;passed+=row['candidates'][index]['correct_offline'];changes+=index!=0
        configs.append({'config':config,'passed':passed,'changed_from_greedy':changes})
    # Ties prefer less intervention, then the verified corpus; no exam values.
    chosen=max(configs,key=lambda r:(r['passed'],-sum(r['config'][k]for k in ['weight','repeat','unreachable']),r['config']['prior']=='verified_training'))
    critic=Critic(chosen['config']['prior']);tasks=read(ROOT/'development.jsonl')
    scores=sorted(critic.inspect(tuple(__import__('ha_protocol').encode(t['reference_code'],t.get('constants')or constants(t['task']),'asm')),tuple(t.get('constants')or constants(t['task'])))['log_prior']for t in tasks)
    result={'config':chosen['config'],'development_correct_candidates':chosen['passed'],'total':panel['total'],
       'feedback_low_prior_threshold':scores[int(.05*(len(scores)-1))],'feedback_quantile':.05,
       'exam_opened':False,'grid':configs,'feedback_max_one_DONE_warning_per_distinct_body':True}
    write(ROOT/'selection.json',result);return result


def panel_summary(panel,selection):
    rows=panel['details'];critic=Critic(selection['config']['prior']);out={}
    for name,config in [('greedy',None),('likelihood',{'weight':0.,'repeat':0.,'unreachable':0.}),('statistics',selection['config'])]:
        passed=0;valid=0;changed=0
        for r in rows:
            if name=='greedy':index=0
            else:index,_=rank([c['generation']for c in r['candidates']],critic,r['pool'],config)
            c=r['candidates'][index];passed+=c['correct_offline'];valid+=c['features'][selection['config']['prior']]['valid'];changed+=index!=0
        out[name]={'passed':passed,'total':len(rows),'valid':valid,'changed_from_greedy':changed}
    out['oracle_best_of_4']={'passed':sum(any(c['correct_offline']for c in r['candidates'])for r in rows),'total':len(rows)}
    wrong=[r for r in rows if not r['initially_correct']]
    out['wrong_start_bottleneck']={'total':len(wrong),'policy_DONE':sum(r['policy_action']=='done'for r in wrong),
       'policy_DONE_but_correct_candidate_exists':sum(r['policy_action']=='done'and any(c['correct_offline']for c in r['candidates'])for r in wrong),
       'no_correct_candidate_among_4':sum(not any(c['correct_offline']for c in r['candidates'])for r in wrong)}
    return out


def rollout(bank,arm,tasks,seeds,selection,*,compiler_rows=None):
    vm=FullVM();lookup={t['id']:t for t in tasks};critic=Critic(selection['config']['prior']);details=[];started=time.monotonic()
    for at in range(0,len(seeds),16):
        items=seeds[at:at+16];sessions=[]
        for j,item in enumerate(items):
            t=lookup[item['task_id']]
            if compiler_rows is not None:
                s=Session(public_task(t),'asm',vm=vm,gate=arm!='greedy_raw');s.initial_history=0;g=compiler_rows[at+j]
                if g.get('codec_error')or g.get('action')!='write':s.history.append({'kind':'compiler_error','generation':g});s.exhausted=True
                else:s.apply_action('write',g['body']);s.history[-1].update(generation=g,profile='frozen_compiler')
                initially_correct=grade(vm,t,s.body)
            else:
                s=make_session(public_task(t),item,vm);s.gate=arm!='greedy_raw';initially_correct=item['intentionally_correct']
            s.exhausted=getattr(s,'exhausted',False);s.initially_correct=initially_correct;s.warned=set();s.candidate_generations=0;s.logical_output_tokens=0;s.critic_warnings=0;sessions.append(s)
        for turn in range(10):
            active=[s for s in sessions if not s.finished and not s.abstained and not s.exhausted and len(s.history)-s.initial_history<10]
            if not active:break
            prompts=[s.request()for s in active];generations=bank.actions(prompts)
            rewriting=[i for i,g in enumerate(generations)if g.get('action')=='write']if arm.startswith('best4')else[]
            candidates=bank.candidates([prompts[i]for i in rewriting],[generations[i]for i in rewriting])if rewriting else[]
            chosen={}
            for i,rows in zip(rewriting,candidates):
                s=active[i];config={'weight':0.,'repeat':0.,'unreachable':0.}if arm=='best4_likelihood'else selection['config']
                index,feature=rank(rows,critic,s.pool,config);chosen[i]=(rows[index],{'selected':index,'features':feature,
                    'candidate_bodies':[r.get('body')for r in rows]})
                s.candidate_generations+=3;s.logical_output_tokens+=sum(len(r.get('generated_token_ids',[]))for r in rows[1:])
            for i,(s,p,g)in enumerate(zip(active,prompts,generations)):
                s.logical_output_tokens+=len(g.get('generated_token_ids',[]));metadata={}
                if i in chosen:g,metadata=chosen[i]
                if g.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':g});s.exhausted=True;continue
                if arm=='best4_feedback'and g['action']=='done'and s.eligibility()[0]:
                    body=tuple(s.body or[]);feature=critic.inspect(body,tuple(s.pool));note=critic.note(feature,selection['feedback_low_prior_threshold'])
                    if note and body not in s.warned:
                        s.warned.add(body);s.critic_warnings+=1;s.observation=note
                        s.history.append({'kind':'critic_rejected_DONE','prompt':p,'generation':g,'observation':note,'revision':s.revision});continue
                kind=s.apply_action(g['action'],g['body']);s.history[-1].update(prompt=p,generation=g,**metadata)
                if arm=='best4_feedback'and kind=='write':
                    f=critic.inspect(tuple(s.body),tuple(s.pool));note=critic.note(f,selection['feedback_low_prior_threshold'])
                    if note:s.observation=note;s.history[-1]['critic_note']=note
        for item,s in zip(items,sessions):
            t=lookup[item['task_id']];correct=grade(vm,t,s.body);eligible=s.eligibility()[0]
            details.append({'id':t['id'],'level':t.get('level',1),'initially_correct':s.initially_correct,
                'program_correct':correct,'finished':s.finished,'eligible':eligible,'pass':correct and s.finished and eligible,
                'abstained':s.abstained,'body':s.body,'history':s.history,'candidate_generations':s.candidate_generations,
                'logical_output_tokens':s.logical_output_tokens,'critic_warnings':s.critic_warnings})
        status('harness',arm=arm,completed=len(details),total=len(seeds),seconds=time.monotonic()-started)
        print(json.dumps({'arm':arm,'states':len(details),'total':len(seeds),'seconds':time.monotonic()-started}),flush=True)
    return {**stats(details),'simple':stats([r for r in details if r['level']==1]),'details':details,
       'candidate_generations':sum(r['candidate_generations']for r in details),'logical_output_tokens':sum(r['logical_output_tokens']for r in details),
       'critic_warnings':sum(r['critic_warnings']for r in details),'seconds':time.monotonic()-started,'hidden_answers_in_runtime':False}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');a=ap.parse_args();ROOT.mkdir(exist_ok=True)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for name,digest in frozen['files'].items():assert sha(ROOT/name)==digest,name
    assert sha(MODEL/'model.mkqb')==frozen['model_packet_sha256']
    if not(ROOT/'selection-protocol.json').exists():write(ROOT/'selection-protocol.json',{
       'frozen_before_candidate_generation':True,'grid_zero_weight_is_no_prior_baseline':True,
       'candidate_selection':'max correct full-ROM development candidates; ties prefer less intervention',
       'feedback_threshold':'5th percentile of development correct references',
       'no_oracle_in_rank_or_feedback':True,'source_hashes':{p.name:sha(p)for p in HERE.glob('ad_*.py')}})
    bank=Bank()
    if a.pilot:
        vm=FullVM();tasks=read(ROOT/'development.jsonl');seeds=read(ROOT/'development-seeds.jsonl')[:8];lookup={t['id']:t for t in tasks}
        prompts=[make_session(public_task(lookup[i['task_id']]),i,vm).request()for i in seeds];started=time.monotonic()
        actions=bank.actions(prompts);rows=bank.candidates(prompts,actions)
        write(ROOT/'pilot.json',{'states':len(rows),'seconds':time.monotonic()-started,'actions':[g.get('action')for g in actions],
               'candidates_per_state':[len(r)for r in rows],'actual':bank.actual});print(json.dumps(json.loads((ROOT/'pilot.json').read_text())));return
    status('development');dev=initial_panel(bank,'development');selection=select(dev);write(ROOT/'development-candidate-summary.json',panel_summary(dev,selection))
    status('sealed_exam');exam=initial_panel(bank,'exam');write(ROOT/'exam-candidate-summary.json',panel_summary(exam,selection))
    tasks=read(ROOT/'exam.jsonl');seeds=read(ROOT/'exam-seeds.jsonl');twins=read(ROOT/'exam-twins.jsonl');twin_seeds=read(ROOT/'exam-twin-seeds.jsonl')
    scratch_tasks=[t for level in [1,2]for t in [t for t in tasks if t['level']==level][:16]]
    compiler_path=ROOT/'scratch-compiler.json'
    if compiler_path.exists():compiler=json.loads(compiler_path.read_text())
    else:compiler=bank.compiler(scratch_tasks);write(compiler_path,compiler)
    for arm in json.loads((ROOT/'policy.json').read_text())['full_harness_arms']:
        path=ROOT/(arm+'-exam.json')
        if path.exists():continue
        main_result=rollout(bank,arm,tasks,seeds,selection)
        twin_result=rollout(bank,arm,twins,twin_seeds,selection)
        scratch=rollout(bank,arm,scratch_tasks,[{'task_id':t['id']}for t in scratch_tasks],selection,compiler_rows=compiler)
        write(path,{'main':main_result,'goal_twins':twin_result,'from_scratch':scratch,'selection_fixed_before_exam':True})
    for name,digest in frozen['files'].items():assert sha(ROOT/name)==digest,name
    assert sha(MODEL/'model.mkqb')==frozen['model_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'inference_only':True,'optimizer_updates':0,'actual_inference':bank.actual,
         'all_frozen_data_and_model_unchanged':True,'device_firmware_modified':False})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:status('failed',error=repr(error));raise
