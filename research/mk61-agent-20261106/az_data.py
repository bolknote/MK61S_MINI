"""New, ROM-verified ASTs; numeric holdouts and old train-only replay."""
import collections
import copy
from decimal import Decimal
import json
import random
import time
from az_common import ROOT,PARENT,DEV_NUMBERS,TEST_NUMBERS,TRAIN_NUMBERS,rows,read,write,save_rows,sha
from ay_data import make,edges,op_count,DEV_EDGES,TEST_EDGES
from ay_finalize import semantic_key
from full_isa_math import UNARY,BINARY,registers
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from ar_spec import expected

ALL_HELD=set(DEV_EDGES+TEST_EDGES)


def numbers(expr):
    if isinstance(expr,str):return set()
    if isinstance(expr,dict):return set()if'pi'in expr else{str(abs(Decimal(expr['constant'])))}
    return set().union(*(numbers(x)for x in expr[1:]))


def leaf(rng,literals,pure):
    if pure or rng.random()<.48:return {'constant':rng.choice(literals)}
    return rng.choice(REGISTERS)


def tree(rng,literals,pure,depth=0,maximum=3):
    if depth>=maximum or(depth and rng.random()<.5):return leaf(rng,literals,pure)
    op=rng.choice(list(UNARY)+list(BINARY))
    return [op,*[tree(rng,literals,pure,depth+1,maximum)for _ in range(1 if op in UNARY else 2)]]


def proposal(rng,family,panel,split):
    held=DEV_NUMBERS if split=='development'else TEST_NUMBERS
    literals=held if panel=='novel'and family!='composition'else TRAIN_NUMBERS
    if family=='composition':
        parent,child=rng.choice(DEV_EDGES if split=='development'else TEST_EDGES)
        sub=[child,*[tree(rng,literals,False,1,2)for _ in range(1 if child in UNARY else 2)]]
        expr=[parent,sub]if parent in UNARY else[parent,sub,tree(rng,literals,False,1,2)]
    elif family=='register':expr=tree(rng,literals,False)
    elif family=='numeric':
        op=rng.choice(list(BINARY));left=rng.choice(REGISTERS);right={'constant':rng.choice(literals)}
        if rng.random()<.35:left=[rng.choice(list(UNARY)),left]
        if rng.random()<.5:left,right=right,left
        expr=[op,left,right]
    else:
        if rng.random()<.6:
            op=rng.choice(list(UNARY));expr=[op,{'constant':rng.choice(literals)}]
        else:expr=tree(rng,literals,True,0,2)
    if op_count(expr)>5:return None
    if family=='constant'and registers(expr):return None
    if family in ['numeric','register','composition']and not registers(expr):return None
    if family=='register'and op_count(expr)<2:return None
    es=edges(expr)
    if family!='composition'and es&ALL_HELD:return None
    if family=='composition':
        allowed=set(DEV_EDGES if split=='development'else TEST_EDGES)
        if not(es&allowed)or es&(ALL_HELD-allowed):return None
    if family in ['constant','numeric']and not numbers(expr):return None
    angle=rng.choice(['RAD','DEG','GRAD'])
    spec={'X':expr,'writes':{rng.choice(REGISTERS):expr}if rng.random()<.18 else{},'angle':angle}
    if not registers(expr):
        try:
            if abs(expected(spec,{})['X'])>1e6:return None
        except (ValueError,ArithmeticError,OverflowError):return None
    return spec


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if(ROOT/'ast-frozen.json').exists():print('AST bank already frozen');return
    vm=FullVM();rng=random.Random(26110821);seen=set();old=[]
    for split in ['train','development','closed']:
        values=rows(PARENT/(split+'-clean.jsonl'));old.extend(values);seen.update(semantic_key(g['spec'])for g in values)
    pilot=ROOT.parent/'spec-diagnostic-v1/goals.json'
    if pilot.exists():seen.update(semantic_key(g['spec'])for g in read(pilot))
    # Reuse only prior *training* trees, never prior control or exam examples.
    grouped=collections.defaultdict(list)
    for g in rows(PARENT/'train-clean.jsonl'):grouped[g['id']].append(g)
    replay_ids=rng.sample(sorted(grouped),600);replay=[]
    for identifier in replay_ids:
        for g in grouped[identifier]:
            item=copy.deepcopy(g);item.update(id='az:replay:'+identifier,source_id=identifier,split='train',panel='known',curriculum='replay',style='legacy')
            replay.append(item)
    save_rows(ROOT/'replay-goals.jsonl',replay)
    quotas={'train':[('known',{'constant':640,'numeric':480})],
            'development':[('known',{'constant':48,'numeric':32,'register':16}),('novel',{'constant':48,'numeric':32,'composition':16})],
            'closed':[('known',{'constant':96,'numeric':96,'register':48}),('novel',{'constant':96,'numeric':96,'composition':48})]}
    output={};started=time.monotonic();counts=collections.Counter()
    for split,panels in quotas.items():
        values=[]
        if split=='train':
            spec={'X':['sin',{'constant':'22'}],'writes':{},'angle':'DEG'}
            anchor=make(vm,spec,'az:train:known:constant:sin22',split,'known','constant',2611082200)
            assert anchor;anchor['curriculum']='new';values.append(anchor);seen.add(semantic_key(spec))
        for panel,families in panels:
            for family,n in families.items():
                accepted=0;attempts=0
                while accepted<n:
                    attempts+=1
                    if attempts>n*7000:raise RuntimeError((split,panel,family,accepted))
                    spec=proposal(rng,family,panel,split)
                    if spec is None or semantic_key(spec)in seen:continue
                    forbidden=DEV_NUMBERS+TEST_NUMBERS if split=='train'else TEST_NUMBERS if split=='development'else[]
                    if numbers(spec['X'])&{str(abs(Decimal(x)))for x in forbidden}:continue
                    g=make(vm,spec,f'az:{split}:{panel}:{family}:{accepted:04}',split,panel,family,rng.randrange(2**31))
                    if not g:counts['domain_ROM_or_length_rejections']+=1;continue
                    g['curriculum']='new';values.append(g);seen.add(semantic_key(spec));accepted+=1
                    if len(values)%100==0:print(json.dumps({'split':split,'ASTs':len(values),'seconds':round(time.monotonic()-started,1)}),flush=True)
        output[split]=values;save_rows(ROOT/(split+'-asts.jsonl'),values)
    write(ROOT/'ast-frozen.json',{'sizes':{s:len(v)for s,v in output.items()},'replay_trees':600,'replay_questions':len(replay),
      'files':{s+'-asts.jsonl':sha(ROOT/(s+'-asts.jsonl'))for s in output},'replay_sha256':sha(ROOT/'replay-goals.jsonl'),
      'heldout_development_literal_values':DEV_NUMBERS,'heldout_closed_literal_values':TEST_NUMBERS,
      'all_prior_exam_and_control_signatures_excluded':True,'pure_constant_sin22_is_training_regression_not_new_exam':True,
      'rejections':dict(counts),'SGD_started':False})
    print(json.dumps({'new_ASTs_frozen':True,'sizes':{s:len(v)for s,v in output.items()},'replay':len(replay),'seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
