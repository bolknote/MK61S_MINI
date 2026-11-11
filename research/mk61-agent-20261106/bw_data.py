"""Unchanged selection panel and previously unseen ROM-verified closed families."""
import collections
import concurrent.futures
import copy
import itertools
import random
import time
from bw_common import ROOT,BV_ROOT,BU_ROOT,read,write,rows,save_rows,sha,signature
from bu_data import known
from bs_data import worker
from be_language import paths3
from full_isa_math import UNARY,BINARY
from full_isa_vm import build
from bl_spec import install
from az_data import tree,numbers

TEST=['0.59327','2.09327','4.59327','37.59327','-0.59327']


def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();seen,occupied=known();literals=set();start=time.monotonic();rng=random.Random(261125111)
    def add(s):
        if s is not None and isinstance(s,dict)and'X'in s:
            seen.add(signature(s));occupied.update(paths3(s['X']));literals.update(numbers(s['X']))
    for root in [BU_ROOT,BV_ROOT]:
        for name in ['train','development','closed','replay','retention','hard','anchors','general','composition-regression']:
            p=root/(name+'.jsonl')
            if p.exists():
                for g in rows(p):
                    for key in ['spec','goal_spec','bad_spec']:add(g.get(key))
        for p in (root/'server-results').glob('*.json'):
            if not(p.stem.startswith(('closed-','development-','fit-','parent-development'))):continue
            v=read(p)
            for panel in ['primary','retention','composition','hard','own','wrong']:
                for r in v.get(panel,{}).get('records',[]):
                    for key in ['declared_spec','initial_spec']:add(r.get(key))
    assert not set(TEST)&literals
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];rng.shuffle(free)
    output=[];used=[]
    def spec(e):return {'X':e,'writes':{f'R{rng.randrange(15):X}':copy.deepcopy(e)}if rng.random()<.35 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
    def job(s,identifier,family):return(s,identifier,'closed',family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),rng.choice(['operation','argument','order']),[])
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for triple in free[:160]:
            batch=[]
            for i in range(40):
                a,b,c=triple;e=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                if i%2:e=[rng.choice(['+','-','*']),e,{'constant':rng.choice(TEST)}]
                s=spec(e)
                if signature(s)in seen:continue
                seen.add(signature(s));batch.append(job(s,f'bw:closed:comp:{len(used):02}:{i:03}','composition'))
            valid=[g for g in pool.map(worker,batch)if g is not None]
            if len(valid)<5:continue
            output.extend(valid[:5]);used.append(triple)
            if len(used)%8==0:print({'closed_families':len(used),'seconds':round(time.monotonic()-start,1)},flush=True)
            if len(used)==32:break
        assert len(used)==32
        for family in ['unary','binary','constant']:
            accepted=0;attempt=0
            while accepted<32:
                batch=[]
                for _ in range(32):
                    attempt+=1
                    if attempt>20000:raise RuntimeError((family,accepted))
                    if family=='unary':e=[list(UNARY)[attempt%len(UNARY)],f'R{rng.randrange(15):X}']
                    elif family=='binary':e=[list(BINARY)[attempt%len(BINARY)],f'R{rng.randrange(15):X}',{'constant':rng.choice(TEST)}]
                    else:e=tree(rng,TEST,True,0,2)
                    s=spec(e)
                    if signature(s)in seen or paths3(e)&set(used):continue
                    seen.add(signature(s));batch.append(job(s,f'bw:closed:{family}:{attempt:06}',family))
                for g in pool.map(worker,batch):
                    if g is not None and accepted<32:output.append(g);accepted+=1
    assert len(output)==256
    save_rows(ROOT/'closed-asts.jsonl',output)
    save_rows(ROOT/'development.jsonl',rows(BV_ROOT/'development.jsonl'))
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in ['closed-asts.jsonl','development.jsonl']},
        'goals':{'development':64,'closed':256},'development_reuses_BV_selection_panel':True,
        'development_previously_evaluated_only_by_UU':True,'closed_composition_families':32,'held_triples':{'closed':list(map(list,used))},
        'fresh_test_literals':TEST,'previous_goals_and_observed_hypotheses_excluded':True,'ROM_checked':True,
        'optimizer_updates':0,'closed_student_generations_seen':False,'seconds':time.monotonic()-start})
    print({'complete':True,'closed_goals':len(output),'closed_families':len(used)},flush=True)


if __name__=='__main__':main()
