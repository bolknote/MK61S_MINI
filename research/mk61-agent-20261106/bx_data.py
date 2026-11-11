"""Retire observed failures, build phase contrasts, freeze wholly new exam ASTs."""
import collections
import concurrent.futures
import copy
import itertools
import random
import time
from bx_common import ROOT,BU_ROOT,BV_ROOT,BW_ROOT,read,write,rows,save_rows,sha,signature
from bu_data import known
from bs_data import worker
from be_language import paths3
from full_isa_math import UNARY,BINARY
from full_isa_vm import build
from bl_spec import install
from bl_vm import CachedVM
from az_data import tree,numbers
from ar_spec import equivalent,verify
from ay_codec import compile_spec,encode

DEV=['0.26483','1.76483','3.26483','43.26483','-0.26483']
TEST=['0.38659','1.88659','3.88659','47.38659','-0.38659']
TRAIN=['0.4375','3.3125','17.6875','42.125','-0.4375','-3.125','0.8125']


def canonical_goal(g,kind):
    g=copy.deepcopy(g)
    if'goal_spec'in g:g['spec']=g.pop('goal_spec')
    g.update(curriculum=kind,reference_body=compile_spec(g['spec'],g['pool']),spec_body=encode(g['spec'],g['pool']))
    return g


def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();started=time.monotonic();rng=random.Random(261126111);seen,occupied=known();known_numbers=set();vm=CachedVM()
    goals={};reports=[]
    def add(s):
        if isinstance(s,dict)and'X'in s:seen.add(signature(s));occupied.update(paths3(s['X']));known_numbers.update(numbers(s['X']))
    for root in [BU_ROOT,BV_ROOT,BW_ROOT]:
        for name in ['train','development','closed','replay','retention','hard','anchors','general','composition-regression','diagnostic']:
            p=root/(name+'.jsonl')
            if not p.exists():continue
            for g in rows(p):
                if all(k in g for k in ['id','spec','pool','task','reference_body']):goals[g['id']]=canonical_goal(g,'retired_regression')
                for key in ['spec','goal_spec','bad_spec']:add(g.get(key))
        for p in(root/'server-results').glob('*.json'):
            if not p.stem.startswith(('closed-','development-','fit-','parent-development','diagnostic-')):continue
            v=read(p);reports.append(v)
            for panel in ['primary','retention','composition','hard','own','wrong']:
                for r in v.get(panel,{}).get('records',[]):
                    for key in ['declared_spec','initial_spec']:add(r.get(key))
    assert not set(DEV+TEST)&known_numbers
    hard=rows(BV_ROOT/'hard.jsonl');save_rows(ROOT/'hard.jsonl',[canonical_goal(g,'exact_repair')for g in hard])
    regression_ids=set();reasons=collections.defaultdict(set)
    for v in reports:
        for panel in ['primary','retention','composition','hard']:
            for r in v.get(panel,{}).get('records',[]):
                if r['id']in goals and not r['program_correct']:regression_ids.add(r['id']);reasons[r['id']].add('observed_initial_error')
        for panel in ['own','wrong']:
            for r in v.get(panel,{}).get('records',[]):
                k=r['task_id']
                if k in goals and r.get('replans')and not r.get('final_spec_intent',{}).get('tested_equal',False):
                    regression_ids.add(k);reasons[k].add('observed_replan_error')
    regression=[goals[k]for k in sorted(regression_ids)]
    assert regression
    anchors=[];seen_anchor=set()
    for g in rows(BV_ROOT/'anchors.jsonl'):
        q=canonical_goal(g,'composition_success'if g['curriculum']=='composition_success'else'retained_success')
        anchors.append(q);seen_anchor.add(q['id'])
    # Broaden successful replay with the retired U/U exam; its labels are not a new test.
    parent=read(BW_ROOT/'server-results/closed-UU.json')
    for r in parent['primary']['records']:
        if not r['program_correct']or r['id']in seen_anchor:continue
        q=canonical_goal(goals[r['id']],'composition_success'if r['family']=='composition'else'retained_success')
        q['verified_parent_success']=True;anchors.append(q);seen_anchor.add(q['id'])
    for g in regression+anchors+[canonical_goal(g,'exact_repair')for g in hard]:
        assert verify(vm,g['reference_body'],g['pool'],g['spec'],g['public_inputs']+g['checker_inputs']+g['audit_inputs'])['status']=='TESTED',g['id']
    save_rows(ROOT/'regressions.jsonl',regression);save_rows(ROOT/'anchors.jsonl',anchors)
    save_rows(ROOT/'general.jsonl',rows(BU_ROOT/'train.jsonl')+rows(BU_ROOT/'replay.jsonl'))
    save_rows(ROOT/'retention.jsonl',rows(BV_ROOT/'retention.jsonl'))
    save_rows(ROOT/'composition-regression.jsonl',rows(BV_ROOT/'composition-regression.jsonl'))
    write(ROOT/'regression-history.json',{'never_reset':True,'all_ids':sorted(regression_ids),'reasons':{k:sorted(v)for k,v in reasons.items()},'all_previous_panels_retired':True})
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];rng.shuffle(free)
    output={s:[]for s in ['train','development','closed']};held={};used_set=set()
    def spec(e):return {'X':e,'writes':{f'R{rng.randrange(15):X}':copy.deepcopy(e)}if rng.random()<.35 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
    def job(s,i,split,family):return(s,i,split,family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),rng.choice(['operation','argument','order']),[])
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for split,literals,need,offset in [('development',DEV,16,0),('closed',TEST,32,64)]:
            used=[]
            for triple in free[offset:offset+128]:
                batch=[]
                for i in range(40):
                    a,b,c=triple;e=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                    if i%2:e=[rng.choice(['+','-','*']),e,{'constant':rng.choice(literals)}]
                    s=spec(e)
                    if signature(s)in seen:continue
                    seen.add(signature(s));batch.append(job(s,f'bx:{split}:comp:{len(used):02}:{i:03}',split,'composition'))
                valid=[g for g in pool.map(worker,batch)if g is not None]
                if len(valid)<5:continue
                output[split].extend(valid[:5]);used.append(triple)
                if len(used)==need:break
            assert len(used)==need;held[split]=list(map(list,used));used_set.update(used)
            print({'stage':split,'families':len(used),'seconds':round(time.monotonic()-started,1)},flush=True)
            n=16 if split=='development'else 32
            for family in ['unary','binary','constant']:
                accepted=0;attempt=0
                while accepted<n:
                    batch=[]
                    for _ in range(32):
                        attempt+=1
                        if attempt>30000:raise RuntimeError((split,family,accepted))
                        if family=='unary':e=[list(UNARY)[attempt%len(UNARY)],f'R{rng.randrange(15):X}']
                        elif family=='binary':e=[list(BINARY)[attempt%len(BINARY)],f'R{rng.randrange(15):X}',{'constant':rng.choice(literals)}]
                        else:e=tree(rng,literals,True,0,2)
                        s=spec(e)
                        if signature(s)in seen or paths3(e)&used_set:continue
                        seen.add(signature(s));batch.append(job(s,f'bx:{split}:{family}:{attempt:06}',split,family))
                    for g in pool.map(worker,batch):
                        if g is not None and accepted<n:output[split].append(g);accepted+=1
        contrast_counts=collections.Counter();contrast_seen=set()
        kinds=['repeat']*36+['order']*24+['arguments']*18+['sign']*18
        for p,kind in enumerate(kinds):
            for attempt in range(600):
                leaf=f'R{rng.randrange(15):X}'if p%2 else{'constant':rng.choice(TRAIN)}
                if kind=='repeat':
                    u=list(UNARY)[p%len(UNARY)];a=[u,leaf];b=[u,[u,copy.deepcopy(leaf)]]
                    if u in ['abs','sign','int','frac']:b=['square',[u,copy.deepcopy(leaf)]]
                elif kind=='order':
                    u,v=rng.sample(safe,2);a=[u,[v,leaf]];b=[v,[u,copy.deepcopy(leaf)]]
                elif kind=='arguments':
                    x,y=rng.sample(TRAIN,2);x={'constant':x};y={'constant':y}
                    a=['*',['reciprocal',x],y];b=['*',['reciprocal',y],x]
                else:
                    u=rng.choice(['pow10','square','asin','neg','ln','log10','reciprocal']);a=[u,leaf];b=[u,['neg',copy.deepcopy(leaf)]]
                left=spec(a);right={**left,'X':b,'writes':{r:copy.deepcopy(b)for r in left['writes']}}
                if any(signature(s)in contrast_seen or paths3(s['X'])&used_set for s in [left,right]):continue
                result=list(pool.map(worker,[job(s,f'bx:contrast:{p:03}:{j}','train','contrast')for j,s in enumerate([left,right])]))
                if any(g is None for g in result):continue
                bank=result[0]['checker_inputs']+result[1]['checker_inputs']
                if not any(equivalent(left,right,[inp]).get('reason')=='COUNTEREXAMPLE'for inp in bank):continue
                for j,g in enumerate(result):
                    g.update(contrast_id=f'bx:contrast:{p:03}',contrast_side=j,contrast_kind=kind,curriculum='matched_contrast');output['train'].append(g);seen.add(signature(g['spec']));contrast_seen.add(signature(g['spec']))
                contrast_counts[kind]+=1;break
            else:raise RuntimeError(('contrast_failed',p,kind))
        attempts=0
        while sum(g['family']=='new_composition'for g in output['train'])<64:
            batch=[]
            for _ in range(32):
                attempts+=1;e=tree(rng,TRAIN,False,0,4);s=spec(e)
                if signature(s)in seen or paths3(e)&used_set:continue
                seen.add(signature(s));batch.append(job(s,f'bx:new:{attempts:06}','train','new_composition'))
            for g in pool.map(worker,batch):
                if g is not None and sum(x['family']=='new_composition'for x in output['train'])<64:g['curriculum']='new_composition';output['train'].append(g)
            if attempts>20000:raise RuntimeError('new_composition_deadline')
    for s,v in output.items():save_rows(ROOT/(s+'-asts.jsonl'),v)
    for g in regression+anchors+rows(ROOT/'general.jsonl')+rows(ROOT/'hard.jsonl')+output['train']:
        assert not paths3(g['spec']['X'])&used_set
        assert not numbers(g['spec']['X'])&set(DEV+TEST)
    files=['hard.jsonl','regressions.jsonl','anchors.jsonl','general.jsonl','retention.jsonl','composition-regression.jsonl','regression-history.json']+[s+'-asts.jsonl'for s in output]
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in files},'goals':{s:len(v)for s,v in output.items()},'held_triples':held,
        'fresh_dev_literals':DEV,'fresh_test_literals':TEST,'regression_goals':len(regression),'anchors':dict(collections.Counter(g['curriculum']for g in anchors)),
        'contrasts':dict(contrast_counts),'all_previous_panels_retired':True,'ROM_checked':True,'student_generations_seen':False,'seconds':time.monotonic()-started})
    print({'complete':True,'goals':{s:len(v)for s,v in output.items()},'regressions':len(regression),'anchors':len(anchors)},flush=True)


if __name__=='__main__':main()
