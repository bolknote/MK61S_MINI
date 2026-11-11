"""Ten repair targets, verified successful replay, and newly held AST families."""
import collections
import concurrent.futures
import copy
import itertools
import random
import time
from decimal import Decimal
from bv_common import ROOT,BU_ROOT,read,write,rows,save_rows,sha,signature
from bu_data import known
from bs_data import worker
from be_language import paths3
from full_isa_math import UNARY,BINARY,registers
from bl_spec import install
from bl_vm import CachedVM
from full_isa_vm import build
from ar_spec import verify,spec_text
from ay_codec import compile_spec,encode
from ha_protocol import canonical
from az_data import tree

DEV=['0.31459','1.81459','3.31459','24.31459','-0.31459']
TEST=['0.48217','1.98217','3.48217','31.48217','-0.48217']


def mutate(expr,mapping,rng):
    if isinstance(expr,str):return mapping.get(expr,expr)
    if isinstance(expr,dict):
        if 'constant'in expr:
            x=Decimal(expr['constant']);d=Decimal(rng.choice(['-1.5','-1.25','-1','-.75','-.5','-.25','-.125','.125','.25','.5','.75','1','1.25','1.5']))
            if x>0 and x+d<=0:d=abs(d)
            return {'constant':canonical(x+d)}
        return copy.deepcopy(expr)
    return [expr[0],*[mutate(x,mapping,rng)for x in expr[1:]]]


def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();vm=CachedVM();rng=random.Random(261124111);start=time.monotonic()
    old=read(BU_ROOT/'server-results/parent-development.json');parent=read(BU_ROOT/'server-results/development-1500.json')
    previous={r['id']:r for r in old['retention']['records']};now={r['id']:r for r in parent['retention']['records']};goals={g['id']:g for g in rows(BU_ROOT/'retention.jsonl')}
    lost=[k for k in previous if previous[k]['program_correct']and not now[k]['program_correct']];assert len(lost)==9
    hard=[copy.deepcopy(goals[k])for k in lost]
    base_primary={r['id']:r for r in old['primary']['records']};devgoals={g['id']:g for g in rows(BU_ROOT/'development.jsonl')}
    unary=[r['id']for r in parent['primary']['records']if r['family']=='unary'and base_primary[r['id']]['program_correct']and not r['program_correct']];assert len(unary)==1
    hard.append(copy.deepcopy(devgoals[unary[0]]))
    for i,g in enumerate(hard):g.update(repair_id=i,source_id=g['id'],id='bv:hard:'+str(i),curriculum='exact_repair')
    save_rows(ROOT/'hard.jsonl',hard)
    # These exact old panels are retired regression/fit controls, not a new test.
    retention=rows(BU_ROOT/'retention.jsonl');composition=rows(BU_ROOT/'closed.jsonl')+rows(BU_ROOT/'development.jsonl');composition=[g for g in composition if g['family']=='composition']
    save_rows(ROOT/'retention.jsonl',retention);save_rows(ROOT/'composition-regression.jsonl',composition)
    parent_records={r['id']:r for n in ['closed-final','development-1500']for r in read(BU_ROOT/'server-results'/ (n+'.json'))['primary']['records']}
    parent_retention={r['id']:r for r in parent['retention']['records']};anchors=[];counts=collections.Counter()
    for values,records,kind in [(retention,parent_retention,'retained_success'),(composition,parent_records,'composition_success')]:
        for g in values:
            r=records[g['id']]
            if not r['program_correct']or r['declared_spec']is None:continue
            bank=g['public_inputs']+g['checker_inputs']+g['audit_inputs']
            if verify(vm,r['program'],g['pool'],g['spec'],bank)['status']!='TESTED':continue
            q=copy.deepcopy(g);q.update(goal_spec=g['spec'],spec=r['declared_spec'],reference_body=r['program'],spec_body=r['generation']['body'],curriculum=kind,verified_parent_success=True)
            assert compile_spec(q['spec'],q['pool'])==q['reference_body']
            anchors.append(q);counts[kind]+=1
    assert counts['retained_success']==102 and counts['composition_success']==185,counts
    save_rows(ROOT/'anchors.jsonl',anchors)
    analysis=[{'id':g['source_id'],'task':g['task'],'expected':spec_text(g['spec']),
               'parent_interpretation':spec_text((now if i<9 else{r['id']:r for r in parent['primary']['records']})[g['source_id']]['declared_spec'])}
              for i,g in enumerate(hard)]
    write(ROOT/'loss-analysis.json',{'nine_lost':analysis[:9],'additional_unary':analysis[9:],'all_nine_are_now_training_fit_targets':True})
    seen,occupied=known()
    def add(s):
        if s is not None:seen.add(signature(s));occupied.update(paths3(s['X']))
    for name in ['train','development','closed','replay','retention']:
        for g in rows(BU_ROOT/(name+'.jsonl')):add(g['spec']);add(g.get('bad_spec'))
    for name in ['parent-development','development-500','development-1500','closed-baseline','closed-final']:
        v=read(BU_ROOT/'server-results'/(name+'.json'))
        for mode in ['primary','retention']:
            for r in v.get(mode,{}).get('records',[]):add(r.get('declared_spec'))
        for mode in ['own','wrong']:
            for r in v.get(mode,{}).get('records',[]):add(r.get('declared_spec'));add(r.get('initial_spec'))
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];rng.shuffle(free)
    reserved_dev=free[:24];reserved_test=free[24:104];held=set(reserved_dev+reserved_test);out={s:[]for s in ['train','development','closed']};families={}
    def job(s,identifier,split,family,exclude=()):
        return(s,identifier,split,family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),rng.choice(['operation','argument','order']),list(exclude))
    def spec(expr):return {'X':expr,'writes':{f'R{rng.randrange(15):X}':expr}if rng.random()<.35 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for split,candidates,need in [('development',reserved_dev,8),('closed',reserved_test,32)]:
            used=[];numbers=DEV if split=='development'else TEST
            for triple in candidates:
                batch=[]
                for i in range(40):
                    a,b,c=triple;e=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                    if i%2:e=[rng.choice(['+','-','*']),e,{'constant':rng.choice(numbers)}]
                    s=spec(e)
                    if signature(s)in seen:continue
                    seen.add(signature(s));batch.append(job(s,f'bv:{split}:comp:{len(used):02}:{i:03}',split,'composition'))
                valid=[g for g in pool.map(worker,batch)if g is not None]
                if len(valid)<5:continue
                out[split].extend(valid[:5]);used.append(triple)
                if len(used)==need:break
            assert len(used)==need,(split,len(used));families[split]=used
            print({'stage':split,'new_families':len(used),'goals':len(out[split]),'seconds':round(time.monotonic()-start,1)},flush=True)
        for split,n,numbers in [('development',8,DEV),('closed',32,TEST)]:
            for family in ['unary','binary','constant']:
                accepted=0;attempt=0
                while accepted<n:
                    batch=[]
                    for i in range(32):
                        attempt+=1
                        if attempt>20000:raise RuntimeError((split,family,accepted))
                        if family=='unary':e=[list(UNARY)[attempt%18],f'R{rng.randrange(15):X}']
                        elif family=='binary':e=[list(BINARY)[attempt%5],f'R{rng.randrange(15):X}',{'constant':rng.choice(numbers)}]
                        else:e=tree(rng,numbers,True,0,2)
                        s=spec(e)
                        if signature(s)in seen or paths3(e)&held:continue
                        seen.add(signature(s));batch.append(job(s,f'bv:{split}:{family}:{attempt:06}',split,family))
                    for g in pool.map(worker,batch):
                        if g is not None and accepted<n:out[split].append(g);accepted+=1
        for i,g in enumerate(hard):
            valid=[];attempt=0
            while len(valid)<8:
                batch=[]
                for j in range(16):
                    attempt+=1
                    if attempt>1000:raise RuntimeError(('repair_variants',i,len(valid)))
                    names=[f'R{k:X}'for k in range(15)];shuffled=names[:];rng.shuffle(shuffled);mapping=dict(zip(names,shuffled))
                    e=mutate(g['spec']['X'],mapping,rng);s={'X':e,'writes':{mapping[r]:e for r in g['spec']['writes']},'angle':g['spec']['angle']}
                    if signature(s)in seen or paths3(e)&held:continue
                    seen.add(signature(s));batch.append(job(s,f'bv:repair:{i:02}:{attempt:03}','train','repair_variant',held))
                for q in pool.map(worker,batch):
                    if q is not None and len(valid)<8:q.update(repair_id=i,curriculum='repair_variant');valid.append(q)
            out['train'].extend(valid)
    for split,v in out.items():save_rows(ROOT/(split+'-asts.jsonl'),v)
    # The old general corpus is replay, not a fresh exam.
    general=rows(BU_ROOT/'train.jsonl')+rows(BU_ROOT/'replay.jsonl');save_rows(ROOT/'general.jsonl',general)
    for g in hard+anchors+general:assert not paths3(g['spec']['X'])&held
    files=['hard.jsonl','retention.jsonl','composition-regression.jsonl','anchors.jsonl','general.jsonl','loss-analysis.json']+[s+'-asts.jsonl'for s in out]
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in files},'counts':dict(counts),'goals':{s:len(v)for s,v in out.items()},
       'hard_nine':9,'additional_unary':1,'held_triples':families,'all_training_excluded_triples':list(map(list,sorted(held))),
       'fresh_dev_literals':DEV,'fresh_test_literals':TEST,'old_panels_are_fit_controls':True,'closed_student_generations_seen':False,
       'ROM_checked':True,'seconds':time.monotonic()-start})
    print({'complete':True,'goals':{s:len(v)for s,v in out.items()},'verified_replay':dict(counts)},flush=True)


if __name__=='__main__':main()
