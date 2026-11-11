"""Fresh closed ASTs with unchanged training and the original held-out triples."""
import collections
import concurrent.futures
import copy
from decimal import Decimal
import json
import random
import time
from bp_common import ROOT,PREVIOUS,PRIOR_RESULTS,PRIORS,TEST_NUMBERS,read,write,rows,save_rows,sha,signature
from bl_spec import install
from bh_editorial import TEMPLATES
from be_language import paths3
from ay_data import make,op_count
from az_data import tree,numbers
from full_isa_math import UNARY,BINARY,registers
from full_isa_vm import FullVM,build
from ar_spec import expected
from av_deepseek import parse_expression
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from ha_protocol import canonical


def worker(item):install();return make(FullVM(),*item)


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();vm=FullVM();rng=random.Random(261119111);started=time.monotonic();seen=set();literals=set()
    for p in list(dict.fromkeys([*PRIORS,PRIOR_RESULTS])):
        for split in ['train','development','closed']:
            for g in rows(p/(split+'-clean.jsonl')):
                seen.add(signature(g['spec']))
                if p==PRIOR_RESULTS and split=='train':literals|=numbers(g['spec']['X'])
    # Exclude observed student hypotheses as well as previous target formulas.
    for a in ['parent_lora','parent_full','lora','full','fixed3000_lora','fixed3000_full']:
        report=read(PRIOR_RESULTS/a/'closed.json')
        for r in report['primary']['records']:
            if r['declared_spec']is not None:seen.add(signature(r['declared_spec']))
        for r in report['self']['records']:
            for k in ['declared_spec','initial_spec']:
                if r.get(k)is not None:seen.add(signature(r[k]))
    banned={canonical(abs(Decimal(x)))for x in TEST_NUMBERS}
    assert not any(canonical(abs(Decimal(x)))in banned for x in literals)
    literals=sorted(literals,key=Decimal);literals+=['-'+x for x in literals if Decimal(x)>0 and '-'+x not in literals]
    ast=read(PREVIOUS/'ast-frozen.json');dev_held={tuple(x)for x in ast['dev_triples']};held={tuple(x)for x in ast['test_triples']};all_held=dev_held|held
    values=[];rejects=collections.Counter()
    quotas=[('known',{'constant':120,'numeric':120,'register':80}),('novel',{'constant':120,'numeric':120,'composition':80})]
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for panel,families in quotas:
            nums=TEST_NUMBERS if panel=='novel'else literals
            for family,n in families.items():
                accepted=0;attempts=0
                while accepted<n:
                    batch=[]
                    for _ in range(min(144,max(16,2*(n-accepted)))):
                        attempts+=1
                        if attempts>n*12000:raise RuntimeError((panel,family,accepted))
                        if family=='composition':
                            a,b,c=rng.choice(sorted(held));expr=[a,[b,[c,rng.choice([f'R{x:X}'for x in range(15)])]]]
                            if rng.random()<.5:expr=['+',expr,{'constant':rng.choice(nums)}]
                        elif family=='numeric':
                            a=rng.choice([f'R{x:X}'for x in range(15)]);b={'constant':rng.choice(nums)}
                            if rng.random()<.4:a=[rng.choice(list(UNARY)),a]
                            if rng.random()<.5:a,b=b,a
                            expr=[rng.choice(list(BINARY)),a,b]
                        else:expr=tree(rng,nums,family=='constant',0,2 if family=='constant'else 3)
                        if op_count(expr)>5 or(family!='constant'and not registers(expr)):continue
                        if family in ['constant','numeric']and not numbers(expr):continue
                        paths=paths3(expr)
                        if family!='composition'and paths&all_held:continue
                        if family=='composition'and paths&dev_held:continue
                        spec={'X':expr,'writes':{rng.choice([f'R{x:X}'for x in range(15)]):expr}if rng.random()<.23 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
                        key=signature(spec)
                        if key in seen:continue
                        if not registers(expr):
                            try:
                                if abs(expected(spec,{})['X'])>1e6:continue
                            except (ValueError,ArithmeticError,OverflowError):continue
                        seen.add(key);identifier=f'bp:closed:{panel}:{family}:{attempts:06}'
                        batch.append((spec,identifier,'closed',panel,family,rng.randrange(2**31)))
                    for g in pool.map(worker,batch):
                        if g is None:rejects['ROM_or_domain']+=1;continue
                        if accepted==n:continue
                        g.update(curriculum='fresh_exam',original_questions=[]);values.append(g);accepted+=1
                    if accepted==n:print(json.dumps({'panel':panel,'family':family,'accepted':n,'seconds':round(time.monotonic()-started,1)}),flush=True)
    editorial=[]
    for turn in range(150):
        if len(editorial)==160:break
        for i,(formula,text)in enumerate(TEMPLATES):
            a=TEST_NUMBERS[(i+turn)%9];b=TEST_NUMBERS[(i+turn+4)%9];expr=parse_expression(formula.format(a=a,b=b))
            spec={'X':expr,'writes':{f'R{(i+turn)%15:X}':expr}if i%4==0 else{},'angle':'DEG'if i%3 else'RAD'}
            key=signature(spec)
            if key in seen or paths3(expr)&all_held:continue
            g=make(vm,spec,f'bp:closed:editorial:{len(editorial):03}','closed','editorial','editorial',rng.randrange(2**31))
            if not g:continue
            q=text.format(a=a,b=b)
            for r in spec['writes']:q+=' Запиши полученный результат в '+r+'.'
            g.update(task=q,pool=pool_for(q),style='editorial',editorial_template=i)
            g['reference_body']=compile_spec(spec,g['pool']);g['spec_body']=encode(spec,g['pool']);editorial.append(g);seen.add(key)
            if len(editorial)==160:break
    assert len(editorial)==160
    structured=[];attempt=0
    while len(structured)<160:
        attempt+=1;expr=tree(rng,TEST_NUMBERS,attempt%3==0,0,2);spec={'X':expr,'writes':{},'angle':rng.choice(['DEG','RAD','GRAD'])};key=signature(spec)
        if key in seen or paths3(expr)&all_held:continue
        g=make(vm,spec,f'bp:closed:structured:{len(structured):03}','closed','structured','structured',rng.randrange(2**31))
        if g:structured.append(g);seen.add(key)
    for name,items in [('closed-asts.jsonl',values),('closed-editorial.jsonl',editorial),('closed-structured.jsonl',structured)]:save_rows(ROOT/name,items)
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in ['closed-asts.jsonl','closed-editorial.jsonl','closed-structured.jsonl']},
          'closed_asts':len(values),'test_triples':sorted(held),'dev_triples':sorted(dev_held),'test_numbers':TEST_NUMBERS,
          'prior_targets_and_observed_hypotheses_excluded':True,'training_not_changed':True,'rejections':dict(rejects),'SGD_started':False,'seconds':time.monotonic()-started})
    print(json.dumps({'ASTs_ready':True,'natural':len(values),'editorial':160,'structured':160}),flush=True)


if __name__=='__main__':main()
