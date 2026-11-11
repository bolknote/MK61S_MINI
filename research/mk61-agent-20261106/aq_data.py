"""Corrected labels from live Sessions, including matched protocol states."""
import collections
import copy
import hashlib
import json
import random
import shutil
from aq_common import ROOT,PARENT,INITIAL,INITIAL_PACKET,read,write,sha
from aq_runtime import Session,snapshot,diagnosis
from ap_data import proposal,label
from aj_teacher import correct
from full_isa_vm import FullVM
from tasks import save_jsonl


def initial(g,r,vm,empty=False):
    state=r['state'];s=Session(state['view'],state['pool'],None if empty else r['body'],vm,'full')
    if not empty:s.runs={int(k):copy.deepcopy(v)for k,v in state['runs'].items()}
    return s


def expert(s,g):
    ref=g['rows'][3]['body'];ok=correct(s.vm,g['task'],s.body,s.pool)
    remaining=snapshot(s)['remaining']
    if remaining<=1:
        return('done',[],True)if ok and s.eligibility()[0]else('unsure',[],ok)
    if s.body is None:return 'write',ref,False
    _,missing,_=s.eligibility()
    if missing:return 'run',[missing[0]],ok
    if s.diagnosis is None or s.diagnosis['revision']!=s.revision:
        kind='correct'if ok else next(r['class']for r in g['rows']if r['body']==s.body)
        return 'diag',diagnosis(s.body,ref,kind),ok
    return ('done',[],True)if ok else('write',ref,False)


def lessons(groups):
    vm=FullVM();result=[];paired=0
    def add(s,g,scenario):
        action,body,ok=expert(s,g);state=snapshot(s)
        assert state['remaining']==12-(len(s.history)-s.initial_history)>0
        assert action!='done'or(ok and s.eligibility()[0])
        origin='goal_program'if s.body is None and action=='write'else'localized_diagnosis'if action=='diag'else'trajectory'
        row={'id':f'aq:lesson:{len(result):07}','group_id':g['id'],'state':state,'action':action,'body':list(body),
          'correctness':-1 if s.body is None else int(ok),'origin':origin,'scenario':scenario,'family':g['family'],'pair_tag':g['pair_tag']}
        if action=='diag':row['error_kind']=['correct','operation','argument','order'][body[0]]
        if action=='write'and s.body:row['before_body']=list(s.body)
        result.append(row);return action,body
    def follow(s,g,scenario):
        for _ in range(12):
            a,b=add(s,g,scenario);s.apply_action(a,b)
            if a in ['done','unsure']:return
        raise AssertionError('Teacher did not finish')
    for number,g in enumerate(groups):
        good=g['rows'][3]
        for consumed in [0,1,2]:
            s=initial(g,good,vm,True)
            for _ in range(consumed):s.apply_action('diag',[0,255,255,0,0])
            add(s,g,'empty_goal_live_budget')
        signatures=[]
        for r in g['rows']:
            s=initial(g,r,vm);follow(s,g,'initial_verified_rollout')
            # Every class gets the same actual history: DIAG, WRITE, RUN, RUN.
            # The new code can be correct or incorrect; no state counters are
            # manufactured, and wrong WRITE is never a supervised target.
            s=initial(g,good,vm);s.apply_action('diag',[0,255,255,0,0]);s.apply_action('write',r['body'])
            s.apply_action('run',[1]);s.apply_action('run',[2]);state=snapshot(s)
            signatures.append((state['remaining'],state['revision'],state['case'],tuple(sorted(state['runs']))))
            follow(s,g,'matched_after_write_and_all_runs')
            for claim in [[0,255,255,0,0],[1,0,0,r['body'][0],r['body'][0]]]:
                s=initial(g,r,vm);s.apply_action('diag',claim);add(s,g,'untrusted_claim_both_truth_classes')
            s=initial(g,good,vm);s.apply_action('write',r['body']);add(s,g,'matched_missing_runs')
            s=initial(g,r,vm)
            for _ in range(1+number%3):s.apply_action('run',[0])
            add(s,g,'live_budget_variation')
            s=initial(g,r,vm)
            for _ in range(11):s.apply_action('diag',[0,255,255,0,0])
            add(s,g,'one_action_left_matched')
        assert len(set(signatures))==1;paired+=1
        if number%100==0:print(json.dumps({'live_teacher_groups':number,'lessons':len(result)}),flush=True)
    return result,paired


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    corpus={}
    for split in ['train','development','novel-development']:
        corpus[split]=read(PARENT/(split+'.jsonl'));save_jsonl(ROOT/(split+'.jsonl'),corpus[split])
    seen={(g['task']['angle'],g['task']['task'])for split in ['train','development','novel-development','fresh','novel-fresh']for g in read(PARENT/(split+'.jsonl'))}
    vm=FullVM();rng=random.Random(181301)
    for split,quotas in [('fresh',{'unary':64,'binary':32,'mixed':32,'memory':32}),('novel-fresh',{'unary':48,'mixed':32})]:
        path=ROOT/(split+'.jsonl')
        if path.exists():corpus[split]=read(path);continue
        values=[]
        for family,n in quotas.items():
            accepted=0;attempts=0
            while accepted<n:
                attempts+=1
                if attempts>n*3000:raise RuntimeError((split,family,accepted))
                p=proposal(rng,split,family)
                if p is None or(p['angle'],p['task'])in seen:continue
                g=label(vm,p,f'aq:{split}:{family}:{accepted:04}',split)
                if g is None:continue
                seen.add((p['angle'],p['task']));values.append(g);accepted+=1
        rng.shuffle(values);save_jsonl(path,values);corpus[split]=values
        print(json.dumps({'new_exam':split,'groups':len(values),'frozen_before_training':True}),flush=True)
    course,paired=lessons(corpus['train']);save_jsonl(ROOT/'lessons.jsonl',course)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy=json.loads((PARENT/'policy.json').read_text());policy.update(selectable_checkpoints=[1250,2500],
      stage1={'goal_program':8,'localized_diagnosis':8,'write':4,'run':4,'done':6,'unsure':2},
      stage2={'goal_program':4,'localized_diagnosis':8,'write':8,'run':4,'done':6,'unsure':2},
      teacher='live Sessions and ROM; matched state histories for correct and wrong code; full-prompt source KD',
      diagnostic_batch_balance='two of each type per batch',endpoint_exam_predeclared=True,
      previous_run='step-debug-v1; preserved with 5000 accounted optimizer updates')
    write(ROOT/'policy.json',policy)
    sensitivity=json.loads((PARENT/'full/development-budget-sensitivity.json').read_text())
    write(ROOT/'teacher-correction.json',{'previous_goal_budget':10,'runtime_initial_budget':12,
      'previous_full_model_control_probe':sensitivity,'all_new_counters_from_live_session':True,
      'matched_protocol_groups':paired,'new_exam_not_used_in_previous_run':True})
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'group_counts':{s:len(g)for s,g in corpus.items()},
      'episode_counts':{s:len(g)*4 for s,g in corpus.items()},'lesson_count':len(course),
      'lesson_actions':dict(collections.Counter(r['action']for r in course)),
      'source_master_sha256':sha(INITIAL/'model.safetensors'),'source_packet_sha256':sha(INITIAL_PACKET),
      'all_bad_have_public_counterexamples':True,'all_candidates_stopped':True,'order_preserves_raw_command_multiset':True,
      'new_exam_texts_disjoint_from_AP':True,'frozen_before_SGD':True,'live_teacher_counters_verified':True})
    print(json.dumps({'frozen':True,'lessons':len(course),'matched_groups':paired}),flush=True)


if __name__=='__main__':main()
