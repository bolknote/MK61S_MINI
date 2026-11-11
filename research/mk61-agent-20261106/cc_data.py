"""Hold out fresh AST combinations and literals before teacher wording or training."""
import collections
import concurrent.futures
import copy
import itertools
import random
import time
from cc_common import ROOT,CA_ROOT,CA_RESULTS,CB_ROOT,CB_RESULTS,BX_ROOT,BZ_ROOT,BY_ROOT,HERE,read,write,rows,save_rows,sha,signature
from bu_data import known
from bs_data import worker
from be_language import paths3
from full_isa_math import UNARY,BINARY
from full_isa_vm import build
from bl_spec import install
from az_data import tree,numbers

DEV=['0.56381','2.06381','3.56381','49.56381','-0.56381']
TEST=['0.74329','2.24329','5.74329','53.74329','-0.74329']
TRAIN=['0.4375','3.3125','17.6875','42.125','-0.4375','-3.125','0.8125']


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();started=time.monotonic();rng=random.Random(261128111);seen,occupied=known();old=[];known_literals=set()
    for root in [ROOT.parent/'spec-phase-adapter-v1',ROOT.parent/'spec-retention-recovery-v1',ROOT.parent/'spec-phase-routing-v1',BX_ROOT,BY_ROOT,BZ_ROOT,CA_ROOT,CB_ROOT]:
        for name in ['train','development','closed','anchors','regressions','retention','general','replay','composition-regression','hard']:
            path=root/(name+'.jsonl')
            if not path.exists():continue
            for g in rows(path):
                for key in ['spec','goal_spec','bad_spec']:
                    s=g.get(key)
                    if isinstance(s,dict)and'X'in s:seen.add(signature(s));occupied.update(paths3(s['X']));known_literals.update(numbers(s['X']))
    assert not set(DEV+TEST)&known_literals
    for name in ['retired-train','train','development','closed','retention']:old+=rows(CB_ROOT/(name+'.jsonl'))
    byid={g['id']:g for g in old};good_by_role={}
    for role in ['parent','final']:
        good=[]
        for split in ['development','closed','retention']:
            file=CB_RESULTS/(f'closed-{role}-original.json'if split=='closed'else f'{role if role=='parent'else 'step-1200'}-{split}-original.json')
            grouped=collections.defaultdict(list)
            for r in read(file)['own']['records']:grouped[r['task_id']].append(r)
            good.extend(k for k,v in grouped.items()if len(v)==2 and all(r['pass']for r in v))
        good_by_role[role]=set(good)
    candidates=sorted(good_by_role['final']);rng.shuffle(candidates);retained=candidates[:32]
    working=sorted(good_by_role['parent']-set(retained));rng.shuffle(working)
    working.sort(key=lambda k:k in good_by_role['final']);retained+=working[:16];assert len(set(retained))==48
    retention=[copy.deepcopy(byid[k])for k in retained]
    training=[copy.deepcopy(g)for g in old if g['id']not in set(retained)]
    good=good_by_role['parent']|good_by_role['final']
    for g in training:g.update(split='train',curriculum='old_success'if g['id']in good else'retired_error')
    save_rows(ROOT/'retention.jsonl',retention);save_rows(ROOT/'retired-train.jsonl',training)
    safe=[op for op in UNARY if op not in ['exp','pow10','sign','int','frac']]
    free=[t for t in itertools.product(safe,repeat=3)if len(set(t))>=2 and t not in occupied];rng.shuffle(free)
    output={s:[]for s in ['train','development','closed']};held={};reserved=set()
    def spec(expr):return {'X':expr,'writes':{f'R{rng.randrange(15):X}':copy.deepcopy(expr)}if rng.random()<.35 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
    def item(s,identifier,split,family,held=()):return(s,identifier,split,family,rng.randrange(2**31),rng.choice(['bracket','named','chain']),rng.choice(['operation','argument','order']),list(held))
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        offset=0
        for split,literals,families in [('development',DEV,8),('closed',TEST,32)]:
            used=[]
            while len(used)<families:
                if offset>=len(free):raise RuntimeError('No unseen viable triples')
                triple=free[offset];offset+=1;batch=[]
                for i in range(32):
                    a,b,c=triple;expr=[a,[b,[c,f'R{rng.randrange(15):X}']]]
                    if i%2:expr=[rng.choice(['+','-','*']),expr,{'constant':rng.choice(literals)}]
                    s=spec(expr)
                    if signature(s)in seen:continue
                    seen.add(signature(s));batch.append(item(s,f'cc:{split}:comp:{len(used):02}:{i:03}',split,'composition'))
                values=[g for g in pool.map(worker,batch)if g is not None]
                if len(values)<5:continue
                output[split].extend(values[:5]);used.append(triple);reserved.add(triple)
            held[split]=list(map(list,used));n=8 if split=='development'else 32
            for family in ['unary','binary','constant']:
                accepted=0;attempt=0
                while accepted<n:
                    batch=[]
                    for _ in range(32):
                        attempt+=1
                        if attempt>30000:raise RuntimeError((split,family,accepted))
                        if family=='unary':expr=[list(UNARY)[attempt%len(UNARY)],f'R{rng.randrange(15):X}']
                        elif family=='binary':expr=[list(BINARY)[attempt%len(BINARY)],f'R{rng.randrange(15):X}',{'constant':rng.choice(literals)}]
                        else:expr=tree(rng,literals,True,0,2)
                        s=spec(expr)
                        if signature(s)in seen or paths3(expr)&reserved:continue
                        seen.add(signature(s));batch.append(item(s,f'cc:{split}:{family}:{attempt:06}',split,family))
                    for g in pool.map(worker,batch):
                        if g is not None and accepted<n:output[split].append(g);accepted+=1
            print({'AST_split':split,'goals':len(output[split]),'seconds':time.monotonic()-started},flush=True)
        attempts=0
        while len(output['train'])<64:
            batch=[]
            for _ in range(32):
                attempts+=1;expr=tree(rng,TRAIN,False,0,4);s=spec(expr)
                if signature(s)in seen or paths3(expr)&reserved:continue
                seen.add(signature(s));batch.append(item(s,f'cc:train:new:{attempts:06}','train','new_composition',reserved))
            for g in pool.map(worker,batch):
                if g is not None and len(output['train'])<64:output['train'].append(g)
            if attempts>20000:raise RuntimeError('New training AST budget exhausted')
    for g in training+retention+output['train']:
        assert not paths3(g['spec']['X'])&reserved
        assert not numbers(g['spec']['X'])&set(DEV+TEST)
    for split,values in output.items():save_rows(ROOT/(split+'-asts.jsonl'),values)
    names=['retention.jsonl','retired-train.jsonl',*[s+'-asts.jsonl'for s in output]]
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in names},'goals':{s:len(v)for s,v in output.items()},
        'held_triples':held,'fresh_dev_literals':DEV,'fresh_test_literals':TEST,'old_training_goals':len(training),'retained_old_successes':48,
        'all_previous_panels_retired':True,'ROM_checked':True,'student_generations_seen':False,'seconds':time.monotonic()-started})
    print(read(ROOT/'ast-frozen.json'),flush=True)


if __name__=='__main__':main()
