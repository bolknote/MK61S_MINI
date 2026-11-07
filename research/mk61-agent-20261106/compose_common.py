"""Executable composition curriculum; bounded ASTs and standard MK-61 only."""
from decimal import Decimal
import hashlib
import json
import random
import re

from course_common import canonical,prefix
from course_teacher import normalize
from harness import check_program,close_number
from tasks import BUILD,compile_expr,family_of,registers_used,value_of

ROOT=BUILD/'composition-v1'
ARMS=['champion','small']


def read(path):return [json.loads(x)for x in path.read_text().splitlines()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def opcount(expr):return 0 if isinstance(expr,str)else 1+sum(opcount(x)for x in expr[1:])


def stack_depth(expr):
    if isinstance(expr,str):return 1
    children=expr[1:]
    return stack_depth(children[0])if len(children)==1 else max(stack_depth(children[0]),1+stack_depth(children[1]))


def substitute(expr,mapping):
    return mapping[expr]if isinstance(expr,str)else[expr[0],*(substitute(x,mapping)for x in expr[1:])]


def rename_task(row,permutation):
    """Rename meanings, code AND numeric fixtures together for real tool feedback."""
    mapping=dict(zip(['R0','R1','R2','R3'],permutation));expr=substitute(row['expression'],mapping)
    fields={}
    for field in ['public_tests','hidden_tests']:
        cases=[]
        for case in row[field]:
            changed={**case,'registers':{mapping.get(k,k):v for k,v in case['registers'].items()}}
            if 'expected_registers'in case:changed['expected_registers']={mapping.get(k,k):v for k,v in case['expected_registers'].items()}
            cases.append(changed)
        fields[field]=cases
    return {**row,'task':re.sub(r'R[0-3]',lambda m:mapping[m.group()],row['task']),
            'expression':expr,'reference_code':compile_expr(expr)+[0x50],**fields}


def make_task(text,expr,rng,identity,*,split,emulator=None):
    code=compile_expr(expr)+[0x50]
    assert len(code)<=105 and stack_depth(expr)<=4
    cases=[];signatures=set();tries=0
    while len(cases)<9:
        tries+=1
        if tries>600:raise ValueError('Cannot build diverse valid calculator cases: '+prefix(expr))
        values=[-13,-7,-3,-1,0,2,5,9,17]if len(cases)<4 else[1,2,3,4,7,11,19]
        registers={r:rng.choice(values)for r in sorted(registers_used(expr))}
        signature=tuple(sorted(registers.items()))
        if signature in signatures:continue
        try:value=value_of(expr,registers)
        except ArithmeticError:continue
        if not value.is_finite()or abs(value)>100000:continue
        case={'registers':registers,'expected_X':str(value.normalize())}
        if emulator and not check_program(emulator,code,[case])['pass']:continue
        cases.append(case);signatures.add(signature)
    if len({x['expected_X']for x in cases})<3:raise ValueError('Degenerate calculation')
    task={'id':identity,'kind':'natural_language','level':opcount(expr),'split':split,
          'task':text,'expression':expr,'reference_code':code,'family':family_of(expr),
          'public_tests':cases[:2],'hidden_tests':cases[2:]}
    return task


def expression_words(expr,style=0):
    """Training-only recursive descriptions; evaluation stories are authored apart."""
    if isinstance(expr,str):return expr
    op,*children=expr;xs=[expression_words(x,style)for x in children]
    if len(xs)==1:
        forms={'abs':['модуль ({})','абсолютную величину ({})','размер ({}) без знака'],
               'neg':['число, противоположное ({})','результат смены знака ({})','отрицание ({})'],
               'square':['квадрат ({})','вторую степень ({})','произведение ({}) на само себя']}
        return forms[op][style%3].format(xs[0])
    forms={'+':['сумму ({a}) и ({b})','результат прибавления ({b}) к ({a})','({a}) плюс ({b})'],
           '-':['разность ({a}) и ({b})','результат вычитания ({b}) из ({a})','({a}) минус ({b})'],
           '*':['произведение ({a}) и ({b})','результат умножения ({a}) на ({b})','({a}) умножить на ({b})'],
           '/':['частное ({a}) и ({b})','результат деления ({a}) на ({b})','({a}) разделить на ({b})']}
    return forms[op][style%3].format(a=xs[0],b=xs[1])


def formula_prompt(expr):
    return ('МК-61. Собери программу по префиксной формуле. Каждый регистр содержит исходное число. '
            'Результат в X, память не изменяй. Ответ <write>байты HEX</write><run/>.\n'
            'Формула: '+prefix(expr)+'\nАссистент: ')
