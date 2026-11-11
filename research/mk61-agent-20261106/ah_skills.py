"""Same-code goal reversals for operators, operands, and short compositions."""
import copy
import math
import random
from decimal import Decimal
from ha_data import number
from natural_data import NAMES
from full_isa_math import UNARY,compile_expr,literal,value,registers
from full_isa_prepare import base_inputs,make_task
from full_isa_protocol import REGISTERS
from ah_teacher import correct
from ha_protocol import constants,encode

OP_PAIRS=[('sqrt','square'),('sin','cos'),('int','frac'),('abs','neg'),('asin','acos'),('exp','pow10'),('atan','sin'),('ln','log10')]


def operation(op,src):
    return src if op=='identity'else ['square',['square',src]]if op=='fourth'else[op,src]


def description(op,src):
    s=str(src['constant'])if isinstance(src,dict)else'текущего X'if src=='R0:X'else src
    if op=='identity':return 'число '+s
    return ('четвёртую степень'if op=='fourth'else NAMES[op])+' '+s


def build(vm,kind,count,seed,seen):
    rng=random.Random(seed);out=[]
    frames={'train':['Вычисли {e}.','Найди {e}.','В X требуется {e}.','Операция: {e}; подготовь программу.','Сделай программу, получающую {e}.','Получи результат: {e}.','Нужен расчёт: {e}.','Выполни {e} на МК-61.'],
      'validation':['Рассчитать нужно {e}.','Запиши вычисление: {e}.','Получить в X надо {e}.'],
      'fresh':['Построй код для вычисления: {e}.','После исполнения нужно получить {e}.','Подготовь расчёт величины: {e}.']}
    for attempt in range(count*200):
        family=['operator_pair','register_binding','constant_binding','power_pair','binary_pair'][attempt%5]
        r,s=rng.sample(REGISTERS,2);source='X'if rng.random()<.4 else'R';angle=rng.choice(['RAD','DEG','GRAD']);frame=rng.choice(frames[kind])
        if family=='operator_pair':
            op1,op2=OP_PAIRS[(attempt//5)%len(OP_PAIRS)];a=b='R0:X'if source=='X'else r
        elif family=='register_binding':
            op1=op2=rng.choice(list(UNARY));a,b=r,s;source='R'
        elif family=='constant_binding':
            op1=op2=rng.choice(['identity','square','abs','neg','sin','cos','atan','asin','acos','reciprocal','frac','int'])
            small=op1 not in ['identity','int'];a={'constant':number(rng,kind,small=small)};b={'constant':number(rng,kind,small=small)};source='constant'
            if a==b:continue
        elif family=='power_pair':
            op1,op2='square','fourth';a=b='R0:X'if source=='X'else r
        else:
            op1,op2=rng.choice([('+','-'),('*','/')]);a=b=None;source='R'
        if family=='binary_pair':
            exprs=[[op,r,s]for op in [op1,op2]];codes=[compile_expr(e)+[0x50]for e in exprs]
            terms=[('сумму'if op=='+'else'разность'if op=='-'else'произведение'if op=='*'else'частное')+f' {r} и {s}'for op in [op1,op2]]
        else:
            leaves=['R0'if x=='R0:X'else x for x in [a,b]]
            exprs=[operation(op,src)for op,src in zip([op1,op2],leaves)];codes=[compile_expr(e)+[0x50]for e in exprs]
            if source=='X':codes=[c[1:]for c in codes]
            terms=[description(op,src)for op,src in zip([op1,op2],[a,b])]
        texts=[frame.format(e=e)+' Память R0–RE сохрани.'for e in terms]
        if texts[0]==texts[1]or any((angle,text)in seen for text in texts):continue
        used=set().union(*(registers(e)for e in exprs));inputs=[base_inputs(rng)for _ in range(6)]
        ops=[op1,op2]
        bounded=any(op in ['asin','acos']for op in ops)
        positive=any(op in ['ln','log10','sqrt']for op in ops)
        grid=['.125','.25','.5','.75','1','2']if positive else['-.75','-.25','.125','.5','.75','1']if bounded else['-3','-.75','.125','.5','2','3']
        for j,state in enumerate(inputs):
            if source=='X':state['X']=grid[j]
            else:
                for k,reg in enumerate(sorted(used)):state[reg]=grid[(j+2*k)%len(grid)]
        valid=True
        try:
            targets=[[value(e,{'R0':state['X']}if source=='X'else state,angle)for state in inputs]for e in exprs]
            valid=all(not isinstance(x,complex)and math.isfinite(x)and abs(x)<1e6 for targets_ in targets for x in targets_)
        except (ValueError,ArithmeticError,OverflowError,TypeError):valid=False
        if not valid:continue
        peers=[]
        for k,(text,code,expr)in enumerate(zip(texts,codes,exprs)):
            t=make_task(vm,code,text,f'ah:{kind}:skill:{attempt}:{k}',family,kind,angle,copy.deepcopy(inputs),kind='ha_task',check_names=['X',*REGISTERS])
            cases=t['public_tests']+t['hidden_tests']
            if any(c['segments'][0]['expected']['status']!='stopped'or not math.isclose(float(c['segments'][0]['expected']['numeric']['X']),target,rel_tol=2e-6,abs_tol=2e-6)for c,target in zip(cases,targets[k])):valid=False;break
            n=1+(len(out)//2)%4;t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
            t.update(expression=expr,source_kind=source,skill_family=family,level=1,goal_twin_group=f'ah:{kind}:skill-pair:{attempt}')
            peers.append(t)
        if not valid:continue
        pool=constants(' '.join(texts))
        for t in peers:t['constants']=pool[:]
        if any(correct(vm,t,encode(peers[1-k]['reference_code'],pool,'asm'),pool)for k,t in enumerate(peers)):continue
        out+=peers;seen.update((angle,t['task'])for t in peers)
        if len(out)==2*count:return out
    raise RuntimeError(('Skill-pair generator exhausted',kind,len(out),count))
