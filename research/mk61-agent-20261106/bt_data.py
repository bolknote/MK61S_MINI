"""Opened diagnostic tasks and a new sealed expression/number exam, before runs."""
import collections
import concurrent.futures
import itertools
import json
import random
import time
from bt_common import ROOT,BS_ROOT,read,write,rows,save_rows,sha,signature
from bl_common import PRIORS,PARENT,ROOT as BL_ROOT
from bp_common import ROOT as BP_ROOT
from bs_data import stream,worker
from br_common import ROOT as BR_ROOT
from be_language import paths3
from full_isa_math import UNARY,BINARY,registers
from ar_spec import infer
from ay_data import op_count
from az_data import tree
from bl_spec import install
from full_isa_vm import build

NUMBERS=['0.74827','1.24827','2.74827','27.74827','-0.74827']


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'data-frozen.json').exists():return
    install();build();rng=random.Random(261122111);seen=set();occupied=set();started=time.monotonic()
    def add(s):
        if s is not None:seen.add(signature(s));occupied.update(paths3(s['X']))
    for p in list(dict.fromkeys([*PRIORS,PARENT,BL_ROOT,BP_ROOT])):
        for split in ['train','development','closed']:
            for g in stream(p/(split+'-clean.jsonl')):add(g['spec'])
    for p in [BR_ROOT,BS_ROOT]:
        for panel in ['train','development','closed','wording','inputs','new_ast','retention','replay-goals']:
            for g in stream(p/(panel+'.jsonl')):
                add(g['spec']);add(g.get('bad_spec'))
    for r in stream(BS_ROOT/'lessons.jsonl'):
        add(r['target_spec']);state=r['state']
        add(state.get('declared_spec'));add(state.get('prior_spec'))
        if state.get('body'):
            try:add(infer(state['body'],state['pool'],state['view']['angle']))
            except (ValueError,ArithmeticError):pass
    # Retire all actually opened hypotheses, not just target trees.
    result_root=BS_ROOT/'server-results'
    for p in [*result_root.glob('closed-*.json'),*result_root.glob('development-*.json')]:
        report=read(p)
        for r in report['primary']['records']:add(r.get('declared_spec'))
        for mode in ['own','wrong','recovery']:
            if report.get(mode):
                for r in report[mode]['records']:add(r.get('declared_spec'));add(r.get('initial_spec'))
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];held=rng.sample(free,6)
    opened=rows(BS_ROOT/'closed.jsonl');diagnostic=[]
    for family,n in [('unary',8),('binary',8),('constant',8),('composition',40)]:
        diagnostic.extend(rng.sample([g for g in opened if g['family']==family],n))
    save_rows(ROOT/'diagnostic.jsonl',diagnostic)
    values=[];counts=collections.Counter()
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for family,n in [('unary',32),('binary',32),('constant',32),('composition',160)]:
            accepted=0;attempt=0
            while accepted<n:
                batch=[]
                for _ in range(min(64,max(16,2*(n-accepted)))):
                    attempt+=1
                    if attempt>n*20000:raise RuntimeError((family,accepted))
                    if family=='unary':expr=[list(UNARY)[attempt%18],f'R{rng.randrange(15):X}']
                    elif family=='binary':expr=[list(BINARY)[attempt%5],f'R{rng.randrange(15):X}',{'constant':rng.choice(NUMBERS)}]
                    elif family=='constant':expr=tree(rng,NUMBERS,True,0,2)
                    else:
                        a,b,c=rng.choice(held);expr=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                        if rng.random()<.6:expr=[rng.choice(['+','-','*']),expr,{'constant':rng.choice(NUMBERS)}]
                    if op_count(expr)>5 or(family!='constant'and not registers(expr)):continue
                    spec={'X':expr,'writes':{f'R{rng.randrange(15):X}':expr}if rng.random()<(.5 if family=='unary'else .2)else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
                    key=signature(spec)
                    if key in seen:continue
                    seen.add(key);identifier=f'bt:closed:{family}:{attempt:06}'
                    batch.append((spec,identifier,'closed',family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),['operation','argument','order'][attempt%3],[]))
                for g in pool.map(worker,batch):
                    if g is None:counts['ROM_or_pair_rejections']+=1;continue
                    if accepted==n:continue
                    values.append(g);accepted+=1
            print(json.dumps({'family':family,'accepted':n,'seconds':round(time.monotonic()-started,1)}),flush=True)
    save_rows(ROOT/'closed.jsonl',values)
    write(ROOT/'data-frozen.json',{'files':{n:sha(ROOT/n)for n in ['diagnostic.jsonl','closed.jsonl']},'diagnostic_goals':64,
        'diagnostic_is_already_opened_BS_exam':True,'closed_goals':256,'closed_composition_goals':160,'fresh_test_triples':held,'fresh_literals':NUMBERS,
        'prior_targets_and_observed_hypotheses_excluded':True,'test_triples_absent_from_known_targets_and_hypotheses':True,
        'all_reference_and_wrong_programs_ROM_checked':True,'optimizer_updates':0,'model_generations_seen':False,'counts':dict(counts)})
    print(json.dumps(read(ROOT/'data-frozen.json')),flush=True)


if __name__=='__main__':main()
