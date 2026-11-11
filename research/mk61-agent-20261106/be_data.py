"""Re-render retired ASTs unambiguously and generate independent fresh holdouts."""
import collections
import concurrent.futures
import copy
from decimal import Decimal
import itertools
import json
import random
import time
from be_common import ROOT,PARENT,PRIORS,DEV_NUMBERS,TEST_NUMBERS,read,write,rows,save_rows,sha
from be_language import question,parse_question,paths3
from be_editorial import TEMPLATES
from ay_data import make,op_count
from az_data import tree,numbers
from ay_finalize import semantic_key
from ay_codec import compile_spec,encode
from az_teacher import pool_for
from ar_spec import expected
from full_isa_math import UNARY,BINARY,registers
from full_isa_vm import FullVM,build
from av_deepseek import parse_expression
from ha_protocol import canonical


def canonical_expr(expr):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return {'pi':True}if'pi'in expr else{'constant':canonical(expr['constant'])}
    return [expr[0],*[canonical_expr(a)for a in expr[1:]]]

def clean_spec(spec):
    expr=canonical_expr(spec['X']);return {'X':expr,'writes':{r:copy.deepcopy(expr)for r in spec['writes']},'angle':spec['angle']}

def cleaned(goal,style,variant):
    g=copy.deepcopy(goal);g['spec']=clean_spec(g['spec']);g['task']=question(g['spec'],style,g['id']+':'+str(variant))
    assert parse_question(g['task'],g['spec']['angle'])==g['spec'],g['id']
    g['pool']=pool_for(g['task']);g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode(g['spec'],g['pool'])
    g.update(style=style,paraphrase=variant,scope_roundtrip_verified=True);return g

def worker(item):
    spec,identifier,split,panel,family,seed=item
    return make(FullVM(),spec,identifier,split,panel,family,seed)

def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'data-frozen.json').exists():return
    rng=random.Random(26110891);build();started=time.monotonic();seen=set();old={};prior_counts={}
    for p in PRIORS:
        n=0
        for split in ['train','development','closed']:
            for g in rows(p/(split+'-clean.jsonl')):seen.add(semantic_key(g['spec']));n+=1
        prior_counts[p.name if p.name!='server-results'else p.parent.name]=n
    for split in ['train','development','closed']:
        for g in rows(PARENT/(split+'-clean.jsonl')):
            s=clean_spec(g['spec']);key=semantic_key(s)
            if key not in old:old[key]={**copy.deepcopy(g),'spec':s,'id':'be:retired:'+g['id'],'source_id':g['id'],'split':'train','panel':'known','curriculum':'cleaned_retired'}
    forbidden={canonical(abs(Decimal(x)))for x in DEV_NUMBERS+TEST_NUMBERS}
    assert not any(numbers(g['spec']['X'])&forbidden for g in old.values())
    train_literals=sorted({canonical(x)for g in old.values()for x in numbers(g['spec']['X'])}|{'0.45','6.875','13.375','27.625','41.875','57.375','73.625'},key=Decimal)
    train_literals+=['-'+x for x in train_literals if Decimal(x)>0]
    occupied=set().union(*(paths3(g['spec']['X'])for g in old.values()))
    safe=[x for x in UNARY if x not in ['exp','pow10','sign','int','frac']]
    candidates=[x for x in itertools.product(safe,repeat=3)if x not in occupied and len(set(x))>=2]
    held=rng.sample(sorted(candidates),12);dev_held=set(held[:6]);test_held=set(held[6:]);all_held=set(held)
    quotas={'train':[('known',{'constant':480,'numeric':480,'register':640})],
        'development':[('known',{'constant':48,'numeric':48,'register':32}),('novel',{'constant':48,'numeric':48,'composition':32})],
        'closed':[('known',{'constant':160,'numeric':160,'register':80}),('novel',{'constant':160,'numeric':160,'composition':80})]}
    output={'train':list(old.values()),'development':[],'closed':[]};rejections=collections.Counter()
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for split,panels in quotas.items():
            for panel,families in panels:
                literals=DEV_NUMBERS if split=='development'and panel=='novel'else TEST_NUMBERS if split=='closed'and panel=='novel'else train_literals
                for family,count in families.items():
                    accepted=0;attempt=0
                    while accepted<count:
                        batch=[]
                        for _ in range(min(160,max(16,2*(count-accepted)))):
                            attempt+=1
                            if attempt>count*20000:raise RuntimeError((split,panel,family,accepted))
                            if family=='composition':
                                a,b,c=rng.choice(sorted(dev_held if split=='development'else test_held))
                                expr=[a,[b,[c,rng.choice([f'R{x:X}'for x in range(15)])]]]
                                if rng.random()<.5:expr=['+',expr,{'constant':rng.choice(literals)}]
                            elif family=='numeric':
                                left=tree(rng,literals,False,1,2)if rng.random()<.4 else rng.choice([f'R{x:X}'for x in range(15)])
                                right={'constant':rng.choice(literals)}
                                if rng.random()<.5:left,right=right,left
                                expr=[rng.choice(list(BINARY)),left,right]
                            else:expr=tree(rng,literals,family=='constant',0,2 if family=='constant'else 3)
                            if op_count(expr)>5 or(family!='constant'and not registers(expr)):continue
                            if family in ['constant','numeric']and not numbers(expr):continue
                            paths=paths3(expr)
                            if family!='composition'and paths&all_held:continue
                            if family=='composition'and paths&(test_held if split=='development'else dev_held):continue
                            spec={'X':expr,'writes':{rng.choice([f'R{x:X}'for x in range(15)]):expr}if rng.random()<.22 else{},'angle':rng.choice(['RAD','DEG','GRAD'])}
                            key=semantic_key(spec)
                            if key in seen:continue
                            if not registers(expr):
                                try:
                                    if abs(expected(spec,{})['X'])>1e6:continue
                                except (ValueError,ArithmeticError,OverflowError):continue
                            seen.add(key);identifier=f'be:{split}:{panel}:{family}:{attempt:06}'
                            batch.append((spec,identifier,split,panel,family,rng.randrange(2**31)))
                        for goal in pool.map(worker,batch):
                            if goal is None:rejections['ROM_domain_or_program_length']+=1;continue
                            if accepted==count:continue
                            goal['curriculum']='new';output[split].append(goal);accepted+=1
                        if accepted%80==0 or accepted==count:
                            value={'split':split,'panel':panel,'family':family,'accepted':accepted,'target':count,'seconds':round(time.monotonic()-started,1)}
                            write(ROOT/'data-status.json',value);print(json.dumps(value),flush=True)
    editorial=[];vm=FullVM()
    for split,n,literals in [('development',32,DEV_NUMBERS),('closed',80,TEST_NUMBERS)]:
        accepted=0
        for turn in range(100):
            if accepted==n:break
            for index,(formula,text)in enumerate(TEMPLATES):
                a=literals[(index+turn)%len(literals)];b=literals[(index+turn+3)%len(literals)]
                expr=parse_expression(formula.format(a=a,b=b));expr=canonical_expr(expr)
                spec={'X':expr,'writes':{f'R{(index+turn)%15:X}':expr}if index%4==0 else{},'angle':'DEG'if index%3 else'RAD'}
                key=semantic_key(spec)
                if key in seen or paths3(expr)&all_held:continue
                g=make(vm,spec,f'be:{split}:editorial:{accepted:03}',split,'editorial','editorial',rng.randrange(2**31))
                if g is None:continue
                task=text.format(a=a,b=b)+' Результат оставь в X.'
                for r in spec['writes']:task+=' Тот же результат запиши в '+r+'.'
                task+=' Остальные регистры памяти сохрани; после вычисления остановись.'
                g.update(task=task,pool=pool_for(task),style='editorial',paraphrase=0,scope_roundtrip_verified=False,
                    curriculum='new_editorial',editorial_template=index,editorial_spec_reviewed_by='Codex')
                g['reference_body']=compile_spec(spec,g['pool']);g['spec_body']=encode(spec,g['pool'])
                seen.add(key);output[split].append(g);editorial.append({'id':g['id'],'task':task,'spec':spec});accepted+=1
                if accepted==n:break
        assert accepted==n,(split,accepted)
    counts={};questions=set();all_keys=set()
    for split,goals in output.items():
        values=[]
        for g in goals:
            if g.get('style')=='editorial':variants=[g]
            else:variants=[cleaned(g,s,i)for i,s in enumerate(['bracket','named','chain'])]if split=='train'else[cleaned(g,['bracket','named','chain'][int(sha_text(g['id'])[:8],16)%3],0)]
            for v in variants:
                q=(v['spec']['angle'],v['task'])
                if q in questions:continue
                questions.add(q);values.append(v)
        keys={semantic_key(g['spec'])for g in values};assert not(keys&all_keys);all_keys.update(keys)
        save_rows(ROOT/(split+'-clean.jsonl'),values);counts[split]={'trees':len(keys),'questions':len(values),
            'panels':dict(collections.Counter(g['panel']for g in values)),'styles':dict(collections.Counter(g['style']for g in values))}
    save_rows(ROOT/'editorial-audit.jsonl',editorial)
    write(ROOT/'data-frozen.json',{'counts':counts,'cleaned_old_ASTs':len(old),'retired_old_development_and_closed':True,
        'prior_rounds':prior_counts,'new_holdouts_exclude_all_prior_signatures':True,'dev_numbers':DEV_NUMBERS,'test_numbers':TEST_NUMBERS,
        'dev_operator_triples':sorted(dev_held),'closed_operator_triples':sorted(test_held),
        'controlled_wordings_roundtrip_parsed':True,'editorial_is_predefined_Codex_templates_not_independent_human_annotation':True,
        'editorial_not_used_in_training':True,'teacher_calls':0,'rejections':dict(rejections),
        'files':{s+'-clean.jsonl':sha(ROOT/(s+'-clean.jsonl'))for s in output},'editorial_audit_sha256':sha(ROOT/'editorial-audit.jsonl'),
        'SGD_started':False,'closed_model_generations_seen':False,'seconds':time.monotonic()-started})
    print(json.dumps({'clean_data_complete':True,'counts':counts}),flush=True)

def sha_text(value):return __import__('hashlib').sha256(value.encode()).hexdigest()

if __name__=='__main__':main()
