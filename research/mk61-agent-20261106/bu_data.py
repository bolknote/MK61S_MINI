"""ROM-checked contrasts, retired own errors, and many held composition families."""
import collections
import concurrent.futures
import copy
import itertools
import random
import time
from bu_common import ROOT,BT_ROOT,BS_ROOT,read,write,rows,save_rows,sha,signature
from bl_common import PRIORS,PARENT,ROOT as BL_ROOT
from bp_common import ROOT as BP_ROOT
from br_common import ROOT as BR_ROOT
from bs_data import stream,worker,continuous
from be_language import paths3
from full_isa_math import UNARY,BINARY,registers
from ar_spec import infer,equivalent
from bl_spec import install
from full_isa_vm import build
from ay_data import op_count
from az_data import tree

DEV=['0.85391','1.35391','2.85391','19.85391','-0.85391']
TEST=['0.92743','1.42743','2.92743','29.92743','-0.92743']
TRAIN=['0.625','1.875','4.375','-0.625','-2.5']


def known():
    seen=set();occupied=set()
    def add(s):
        if s is not None:seen.add(signature(s));occupied.update(paths3(s['X']))
    for p in list(dict.fromkeys([*PRIORS,PARENT,BL_ROOT,BP_ROOT])):
        for split in ['train','development','closed']:
            for g in stream(p/(split+'-clean.jsonl')):add(g['spec'])
    for p in [BR_ROOT,BS_ROOT,BT_ROOT]:
        for panel in ['train','development','closed','wording','inputs','new_ast','retention','replay-goals','diagnostic']:
            for g in stream(p/(panel+'.jsonl')):add(g['spec']);add(g.get('bad_spec'))
    for r in stream(BS_ROOT/'lessons.jsonl'):
        add(r['target_spec']);s=r['state'];add(s.get('declared_spec'));add(s.get('prior_spec'))
        if s.get('body'):
            try:add(infer(s['body'],s['pool'],s['view']['angle']))
            except (ValueError,ArithmeticError):pass
    for p in [BS_ROOT/'server-results',BT_ROOT/'server-results']:
        for f in list(p.glob('closed-*.json'))+list(p.glob('development-*.json'))+list(p.glob('diagnostic-*.json')):
            if f.name=='diagnostic-half-parity.json':continue
            v=read(f)
            if 'primary'not in v:continue
            for r in v['primary']['records']:add(r.get('declared_spec'))
            for mode in ['own','wrong','gold','recovery']:
                if v.get(mode):
                    for r in v[mode]['records']:add(r.get('declared_spec'));add(r.get('initial_spec'))
    return seen,occupied


def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'inputs-frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();seen,occupied=known();rng=random.Random(261123111);start=time.monotonic();counts=collections.Counter()
    safe=[o for o in UNARY if o not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];rng.shuffle(free)
    reserved_dev=free[:32];reserved_test=free[32:112];allheld=set(reserved_dev+reserved_test)
    output={k:[]for k in ['train','development','closed']};accepted_triples={}
    def item(spec,identifier,split,family,held=()):
        return (spec,identifier,split,family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),rng.choice(['operation','argument','order']),list(held))
    def spec(expr):return {'X':expr,'writes':{f'R{rng.randrange(15):X}':copy.deepcopy(expr)}if rng.random()<.35 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        # More held families at the same 160 closed composition goals.
        for split,candidates,need in [('development',reserved_dev,16),('closed',reserved_test,32)]:
            family_rows=[];used=[];numbers=DEV if split=='development'else TEST
            for triple in candidates:
                jobs=[]
                for attempt in range(40):
                    a,b,c=triple;expr=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                    if attempt%2:expr=[rng.choice(['+','-','*']),expr,{'constant':rng.choice(numbers)}]
                    s=spec(expr);key=signature(s)
                    if key in seen:continue
                    seen.add(key);jobs.append(item(s,f'bu:{split}:comp:{len(used):02}:{attempt:03}',split,'composition'))
                valid=[g for g in pool.map(worker,jobs)if g is not None]
                if len(valid)<5:counts[split+'_unviable_triples']+=1;continue
                family_rows.extend(valid[:5]);used.append(triple)
                if len(used)==need:break
            assert len(used)==need,(split,len(used));output[split].extend(family_rows);accepted_triples[split]=used
            print({'stage':split,'held_families':len(used),'goals':len(family_rows),'seconds':round(time.monotonic()-start,1)},flush=True)
        for split,n,numbers in [('development',16,DEV),('closed',32,TEST),('train',32,TRAIN)]:
            for family in ['unary','binary','constant']:
                accepted=0;attempt=0
                while accepted<n:
                    jobs=[]
                    for j in range(32):
                        attempt+=1
                        if attempt>20000:raise RuntimeError((split,family,accepted))
                        if family=='unary':expr=[list(UNARY)[attempt%18],f'R{rng.randrange(15):X}']
                        elif family=='binary':expr=[list(BINARY)[attempt%5],f'R{rng.randrange(15):X}',{'constant':rng.choice(numbers)}]
                        else:expr=tree(rng,numbers,True,0,2)
                        if not registers(expr)and family!='constant':continue
                        s=spec(expr);key=signature(s)
                        if key in seen or paths3(expr)&allheld:continue
                        seen.add(key);jobs.append(item(s,f'bu:{split}:{family}:{attempt:06}',split,family,allheld if split=='train'else()))
                    for g in pool.map(worker,jobs):
                        if g is not None and accepted<n:output[split].append(g);accepted+=1
                print({'stage':split,'family':family,'accepted':n},flush=True)
        # Reuse known wrong questions only as retired training targets.
        old=read(BT_ROOT/'server-results/closed-baseline.json');wrong_ids={r['id']for r in old['primary']['records']if not r['program_correct']}
        retired=[g for g in rows(BT_ROOT/'closed.jsonl')if g['id']in wrong_ids and not(paths3(g['spec']['X'])&allheld)]
        for g in retired:
            g=copy.deepcopy(g);g.update(id='bu:retired:'+g['id'],split='train',curriculum='retired_error');output['train'].append(g)
        # Matched order contrasts. Neither member may contain a held triple.
        pairs=0;attempt=0
        while pairs<128:
            attempt+=1
            if attempt>20000:raise RuntimeError(('not_enough_contrasts',pairs))
            a,b,c=rng.sample(safe,3);leaf=f'R{rng.randrange(15):X}'
            left=[a,[b,[c,leaf]]];right=[b,[a,[c,leaf]]]
            if paths3(left)&allheld or paths3(right)&allheld:continue
            s=spec(left);t={**s,'X':right,'writes':{r:right for r in s['writes']}}
            if any(signature(x)in seen for x in [s,t]):continue
            result=list(pool.map(worker,[item(x,f'bu:contrast:{pairs:03}:{j}','train','composition',allheld)for j,x in enumerate([s,t])]))
            if any(g is None for g in result):continue
            common=[]
            for inp in result[0]['checker_inputs']+result[1]['checker_inputs']:
                q=equivalent(s,t,[inp])
                if q.get('reason')=='COUNTEREXAMPLE':common.append(inp)
            if not common:continue
            for j,g in enumerate(result):
                seen.add(signature(g['spec']));g.update(contrast_id=f'order:{pairs:03}',contrast_side=j,curriculum='order_pair');output['train'].append(g)
            pairs+=1
        # Additional varied composition trees, including binary structure.
        target=512;attempt=0
        while len(output['train'])<target:
            jobs=[]
            for j in range(32):
                attempt+=1;expr=tree(rng,TRAIN,False,0,4)
                if not 2<=op_count(expr)<=5 or not registers(expr)or paths3(expr)&allheld:continue
                s=spec(expr)
                if signature(s)in seen:continue
                seen.add(signature(s));jobs.append(item(s,f'bu:train:fresh:{attempt:06}','train','composition',allheld))
            for g in pool.map(worker,jobs):
                if g is not None and len(output['train'])<target:output['train'].append(g)
            if attempt>20000:raise RuntimeError(('variety',len(output['train'])))
    legacy=rows(BL_ROOT/'train-clean.jsonl');rng.shuffle(legacy);replay=[];quota=collections.Counter()
    for g in legacy:
        kind='composition'if op_count(g['spec']['X'])>=3 else'other'
        if quota[kind]>=1024 or paths3(g['spec']['X'])&allheld:continue
        g=copy.deepcopy(g);g.update(id='bu:replay:'+str(len(replay)),split='train',curriculum='replay');replay.append(g);quota[kind]+=1
        if len(replay)==2048:break
    assert len(replay)==2048
    retained=rows(BL_ROOT/'development-clean.jsonl');rng.shuffle(retained);retained=[g for g in retained if not paths3(g['spec']['X'])&allheld][:128]
    assert len(retained)==128;save_rows(ROOT/'replay.jsonl',replay);save_rows(ROOT/'retention.jsonl',retained)
    for split,v in output.items():save_rows(ROOT/(split+'-asts.jsonl'),v)
    files=['replay.jsonl','retention.jsonl']+[s+'-asts.jsonl'for s in output]
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in files},'goals':{k:len(v)for k,v in output.items()},
        'held_triples':accepted_triples,'all_training_excluded_triples':list(map(list,sorted(allheld))),
        'closed_composition_families':32,'dev_composition_families':16,'retired_wrong_goals':len(retired),'order_pairs':pairs,
        'fresh_dev_literals':DEV,'fresh_test_literals':TEST,'counts':dict(counts),'ROM_checked':True,'model_generations_seen':False,'seconds':time.monotonic()-start})
    print({'complete':True,'goals':{k:len(v)for k,v in output.items()},'pairs':pairs},flush=True)


if __name__=='__main__':main()
