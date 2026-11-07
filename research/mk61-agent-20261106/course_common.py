"""Small prefix representation and text-only calculator prompts for the curriculum."""
import re
import random

from harness import check_program,initial_prompt
from prompt_variants import without_public_examples
from tasks import compile_expr,program_text,registers_used,value_of

ARITY={'+':2,'-':2,'*':2,'/':2,'abs':1,'neg':1,'square':1}


def prefix(expr):
    return expr if isinstance(expr,str)else expr[0]+' '+' '.join(prefix(x)for x in expr[1:])


def parse_prefix(text):
    words=text.strip().split()
    if len(words)>40:raise ValueError('Prefix expression too long')
    cursor=0
    def read(depth=0):
        nonlocal cursor
        if cursor>=len(words)or depth>8:raise ValueError('Incomplete prefix expression')
        token=words[cursor];cursor+=1
        if re.fullmatch(r'R[0-3]',token):return token
        if token not in ARITY:raise ValueError('Unknown prefix token')
        return [token,*(read(depth+1)for _ in range(ARITY[token]))]
    result=read()
    if cursor!=len(words):raise ValueError('Trailing prefix tokens')
    return result


def calc_prompt(text):
    return ('Разбери условие для МК-61. Ответ только <calc>операции и регистры</calc>. '
            'Префиксная запись: операция перед аргументами. Операции: + - * / abs neg square. '
            '\nУсловие: '+text+'\nОтвет: ')


def program_prompt(task,*,observation=None):
    prompt=without_public_examples(initial_prompt(task,examples=False,observation=observation))
    return re.sub(r'<plan>.*?</plan>','',prompt,flags=re.S)


def answer(task):
    # The model predicts this compact intermediate result itself. It is never
    # supplied by a parser, reference answer or external compiler at inference.
    return '<calc>'+prefix(task['expression'])+'</calc><write>'+program_text(task['reference_code'])+'</write><run/>'


def canonical(expr):
    if isinstance(expr,str):return expr
    op,*args=expr;children=[canonical(x)for x in args]
    if op in ['+','*']:children.sort()
    return op+'('+','.join(children)+')'


def has_sign(expr):
    return isinstance(expr,list)and(expr[0]in['abs','neg']or any(has_sign(x)for x in expr[1:]))


def numeric_cases(expr,rng,*,count=9):
    rows=[];tries=0
    while len(rows)<count:
        tries+=1
        if tries>500:raise ValueError('Cannot sample safe numerical cases')
        # Signed numbers are essential to distinguish abs from identity.
        values=[-19,-11,-5,-2,0,1,3,7,12,21]if has_sign(expr)else[1,2,3,4,6,9,13,17,24]
        if len(rows)==0 and has_sign(expr):values=[-19,-11,-5,-2]
        if len(rows)==1 and has_sign(expr):values=[1,3,7,12,21]
        registers={r:rng.choice(values)for r in sorted(registers_used(expr))}
        try:v=value_of(expr,registers)
        except ArithmeticError:continue
        if not v.is_finite()or abs(v)>1e6:continue
        if not has_sign(expr)and v<0:continue
        rows.append({'registers':registers,'expected_X':str(v.normalize())})
    return rows


def make_task(text,expr,rng,identity,*,level,split,emulator=None):
    cases=numeric_cases(expr,rng)
    task={'id':identity,'kind':'natural_language','level':level,'split':split,'task':text,
          'expression':expr,'reference_code':compile_expr(expr)+[0x50],
          'public_tests':cases[:2],'hidden_tests':cases[2:]}
    if emulator is not None and not check_program(emulator,task['reference_code'],cases)['pass']:
        raise ValueError('Numerical reference does not execute correctly: '+identity)
    return task
