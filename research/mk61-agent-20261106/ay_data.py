"""Independent random expression trees, reserved operator edges, ROM fixtures."""
import collections
import hashlib
import json
import math
import random
import time

from ay_common import ROOT,DEV_EDGES,TEST_EDGES,write,save_rows,sha
from full_isa_math import UNARY,BINARY,registers,words,value
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from ar_spec import expected,verify,equivalent,infer
from ha_protocol import constants
from ay_codec import encode,decode,compile_spec

CONSTANTS=['-2','-1','0.25','0.5','1','1.5','2','2.5','3','4','10']
ALL_HELD=set(DEV_EDGES+TEST_EDGES)


def key(spec):return json.dumps([spec['angle'],spec['X'],sorted(spec['writes'])],sort_keys=True,separators=(',',':'))


def edges(expr):
    if not isinstance(expr,list):return set()
    result=set()
    for child in expr[1:]:
        if isinstance(child,list):result.add((expr[0],child[0]))
        result|=edges(child)
    return result


def op_count(expr):return 0 if not isinstance(expr,list)else 1+sum(op_count(x)for x in expr[1:])


def leaf(rng):
    if rng.random()<.18:return {'constant':rng.choice(CONSTANTS)}
    return rng.choice(REGISTERS)


def tree(rng,depth=0,maximum=3):
    if depth>=maximum or(depth and rng.random()<.45):return leaf(rng)
    op=rng.choice(list(UNARY)+list(BINARY))
    return [op,*[tree(rng,depth+1,maximum)for _ in range(1 if op in UNARY else 2)]]


def proposal(rng,family,panel,split):
    if panel=='novel':
        parent,child=rng.choice(DEV_EDGES if split=='development'else TEST_EDGES)
        sub=[child,*[tree(rng,1,2)for _ in range(1 if child in UNARY else 2)]]
        expr=[parent,sub]if parent in UNARY else[parent,sub,tree(rng,1,2)]
    elif family=='unary':expr=[rng.choice(list(UNARY)),leaf(rng)]
    elif family=='binary':expr=[rng.choice(list(BINARY)),leaf(rng),leaf(rng)]
    else:expr=tree(rng)
    if not registers(expr)or op_count(expr)>5:return None
    if family=='composite'and op_count(expr)<2:return None
    es=edges(expr)
    if panel=='known'and es&ALL_HELD:return None
    if panel=='novel':
        allowed=set(DEV_EDGES if split=='development'else TEST_EDGES)
        if not(es&allowed)or es&(ALL_HELD-allowed):return None
    angle=rng.choice(['RAD','DEG','GRAD'])
    writes={rng.choice(REGISTERS):expr}if family=='memory'else{}
    return {'X':expr,'writes':writes,'angle':angle}


def fixture_inputs(spec,seed,n):
    rng=random.Random(seed);out=[]
    atoms=[-2.75,-1.5,-.625,0,.25,.75,1.25,2.25,3.5]
    for attempt in range(1200):
        inputs={r:str(round(rng.choice(atoms)if attempt<20 else rng.uniform(-3.5,3.5),4))for r in REGISTERS}
        inputs.update(X='0.37',Y='-.82',Z='1.23',T='-2.41')
        try:
            result=expected(spec,inputs)
            if abs(result['X'])>1e6:continue
        except (ValueError,ArithmeticError,KeyError,OverflowError):continue
        out.append(inputs)
        if len(out)==n:return out
    return None


def canonical_task(spec):
    text='Вычисли '+words(spec['X'])+'. Результат оставь в X. '
    for r in spec['writes']:text+='Тот же результат запиши в '+r+'. '
    return text+'Остальные регистры памяти сохрани; после вычисления остановись.'


def make(vm,spec,identifier,split,panel,family,seed):
    text=canonical_task(spec);pool=constants(text)
    try:
        body=compile_spec(spec,pool);encoded=encode(spec,pool)
        assert decode(encoded,pool,spec['angle'])==spec
    except (ValueError,ArithmeticError):return None
    if len(body)>38:return None
    audit_n=8 if split=='train' else 16 if split=='development' else 32
    cases=fixture_inputs(spec,seed,2+16+audit_n)
    if not cases:return None
    check=verify(vm,body,pool,spec,cases)
    if check['status']!='TESTED':return None
    try:
        implied=infer(body,pool,spec['angle'])
        if not equivalent(implied,spec,cases)['tested_equal']:return None
    except (ValueError,ArithmeticError):return None
    return {'id':identifier,'split':split,'panel':panel,'family':family,'spec':spec,'canonical_task':text,
            'pool':pool,'reference_body':body,'spec_body':encoded,'public_inputs':cases[:2],
            'checker_inputs':cases[2:18],'audit_inputs':cases[18:],
            'operator_edges':[list(x)for x in sorted(edges(spec['X']))]}


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():print('AST bank already frozen');return
    vm=FullVM();rng=random.Random(26110801);seen=set();output={};counts=collections.Counter()
    # Exclude the opened 32-condition pilot by exact spec/angle/store signature.
    old=ROOT.parent/'spec-diagnostic-v1/goals.json'
    if old.exists():seen.update(key(g['spec'])for g in json.loads(old.read_text()))
    quotas={'train':[('known',{'unary':384,'binary':384,'composite':512,'memory':320})],
            'development':[('known',{'unary':24,'binary':24,'composite':56,'memory':24}),('novel',{'composite':48,'memory':16})],
            'closed':[('known',{'unary':32,'binary':32,'composite':64,'memory':32}),('novel',{'composite':112,'memory':48})]}
    started=time.monotonic()
    for split,panels in quotas.items():
        values=[]
        for panel,families in panels:
            for family,n in families.items():
                accepted=0;attempts=0
                while accepted<n:
                    attempts+=1
                    if attempts>n*6000:raise RuntimeError((split,panel,family,accepted))
                    spec=proposal(rng,family,panel,split)
                    if spec is None or key(spec)in seen:continue
                    g=make(vm,spec,f'ay:{split}:{panel}:{family}:{accepted:04}',split,panel,family,rng.randrange(2**31))
                    if g is None:counts['rejected_domain_or_ROM_or_length']+=1;continue
                    seen.add(key(spec));values.append(g);accepted+=1;counts[split+':'+family]+=1
                    if len(values)%100==0:print(json.dumps({'split':split,'accepted':len(values),'seconds':round(time.monotonic()-started,1)}),flush=True)
        output[split]=values;save_rows(ROOT/(split+'-asts.jsonl'),values)
    assert all(not(edges(g['spec']['X'])&ALL_HELD)for g in output['train'])
    write(ROOT/'ast-frozen.json',{'seed':26110801,'files':{s+'-asts.jsonl':sha(ROOT/(s+'-asts.jsonl'))for s in output},
                                 'counts':dict(counts),'sizes':{s:len(v)for s,v in output.items()},
                                 'opened_pilot_excluded_by_signature':True,'dev_edges':DEV_EDGES,'closed_edges':TEST_EDGES,
                                 'all_references_checked_against_real_ROM':True,'model_generations_seen':False})
    print(json.dumps({'AST_bank_frozen':True,'sizes':{s:len(v)for s,v in output.items()},'seconds':time.monotonic()-started}),flush=True)


if __name__=='__main__':main()
