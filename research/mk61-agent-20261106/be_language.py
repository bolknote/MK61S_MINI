"""Scope-explicit Russian renderers and a separate recursive parser for cleanup."""
import copy
import hashlib
import re
from ha_protocol import canonical
from full_isa_math import UNARY,BINARY

NAMES={'neg':['противоположное число','число с обратным знаком'],'pow10':['десять в степени'],
 'exp':['экспонента'],'log10':['десятичный логарифм'],'ln':['натуральный логарифм'],
 'asin':['арксинус'],'acos':['арккосинус'],'atan':['арктангенс'],'sin':['синус'],'cos':['косинус'],'tan':['тангенс'],
 'sqrt':['квадратный корень'],'square':['квадрат'],'reciprocal':['обратная величина'],
 'abs':['модуль'],'sign':['знак'],'int':['целая часть с отсечением к нулю'],'frac':['дробная часть с сохранением знака']}
PAIRS={'+':'сумма значений','-':'разность значений','*':'произведение значений','/':'частное значений','pow':'степень'}
INFIX={'+':'плюс','-':'минус','*':'умножить на','/':'разделить на','pow':'в степени'}
LAST='полученный результат'

def choice(values,identity):return values[int(hashlib.sha256(identity.encode()).hexdigest()[:8],16)%len(values)]

def expression(expr,style='bracket',identity=''):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return 'пи'if'pi'in expr else canonical(expr['constant'])
    op,*args=expr;children=[expression(a,style,identity+':'+str(i))for i,a in enumerate(args)]
    if op in UNARY:return choice(NAMES[op],identity)+' ('+children[0]+')'
    if style=='named':
        if op=='pow':return 'степень с основанием ('+children[0]+') и показателем ('+children[1]+')'
        return PAIRS[op]+' ('+children[0]+') и ('+children[1]+')'
    return '('+children[0]+' '+INFIX[op]+' '+children[1]+')'

def chain(expr,identity):
    if not isinstance(expr,list):return [expression(expr,'named',identity)]
    op,*args=expr
    branches=[i for i,a in enumerate(args)if isinstance(a,list)]
    if len(branches)!=1:return [expression(expr,'named',identity)]
    i=branches[0];before=chain(args[i],identity+':child');shell=copy.deepcopy(expr);shell[i+1]=LAST
    return before+[expression(shell,'named',identity+':shell')]

def question(spec,style='bracket',identity=''):
    if style=='chain':
        parts=chain(spec['X'],identity);text='Сначала вычисли: '+parts[0]
        for part in parts[1:]:text+='. Затем вычисли: '+part
    else:text=choice(['Вычисли: ','Найди: '],identity)+expression(spec['X'],style,identity)
    text+='. Результат оставь в X.'
    for register in spec['writes']:text+=' Тот же результат запиши в '+register+'.'
    return text+' Остальные регистры памяти сохрани; после вычисления остановись.'


class Parser:
    def __init__(self,text,last=None):self.text=re.sub(r'\bR\s+([A-E])\b',r'R\1',text);self.at=0;self.last=last
    def take(self,value):
        while self.at<len(self.text)and self.text[self.at].isspace():self.at+=1
        if self.text.startswith(value,self.at):self.at+=len(value);return True
        return False
    def need(self,value):
        if not self.take(value):raise ValueError('EXPECTED '+value+' AT '+self.text[self.at:self.at+30])
    def group(self):self.need('(');x=self.expr();self.need(')');return x
    def expr(self):
        if self.take(LAST):
            if self.last is None:raise ValueError('NO_PREVIOUS_RESULT')
            return copy.deepcopy(self.last)
        for name,op in sorted([(n,k)for k,v in NAMES.items()for n in v],key=lambda x:-len(x[0])):
            if self.take(name):return [op,self.group()]
        if self.take('степень с основанием'):
            a=self.group();self.need('и показателем');return ['pow',a,self.group()]
        for op,name in PAIRS.items():
            if op!='pow'and self.take(name):
                a=self.group();self.need('и');return [op,a,self.group()]
        if self.take('('):
            a=self.expr();op=None
            for k,v in INFIX.items():
                if self.take(v):op=k;break
            if op is None:raise ValueError('BINARY_OPERATOR')
            b=self.expr();self.need(')');return [op,a,b]
        if self.take('пи'):return {'pi':True}
        while self.at<len(self.text)and self.text[self.at].isspace():self.at+=1
        m=re.match(r'R[0-9A-E]\b',self.text[self.at:])
        if m:self.at+=len(m.group());return m.group()
        m=re.match(r'-?(?:\d+(?:\.\d*)?|\.\d+)',self.text[self.at:])
        if m:self.at+=len(m.group());return {'constant':canonical(m.group())}
        raise ValueError('LEAF '+self.text[self.at:self.at+40])
    def parse(self):
        result=self.expr()
        if self.text[self.at:].strip():raise ValueError('TRAILING_EXPRESSION')
        return result

def parse_question(text,angle):
    core,separator,suffix=text.partition('. Результат оставь в X.')
    if not separator:raise ValueError('RESULT_CONTRACT')
    for start in ['Вычисли: ','Найди: ','Сначала вычисли: ']:
        if core.startswith(start):core=core[len(start):];break
    else:raise ValueError('QUESTION_PREFIX')
    current=None
    for part in core.split('. Затем вычисли: '):current=Parser(part,current).parse()
    registers=re.findall(r'Тот же результат запиши в (R[0-9A-E])\.',suffix)
    expected=''.join(' Тот же результат запиши в '+r+'.'for r in registers)+' Остальные регистры памяти сохрани; после вычисления остановись.'
    if suffix!=expected:raise ValueError('TRAILING_CONTRACT')
    return {'X':current,'writes':{r:current for r in registers},'angle':angle}

def paths3(expr):
    if not isinstance(expr,list):return set()
    result=set()
    for child in expr[1:]:
        if isinstance(child,list):
            for grandchild in child[1:]:
                if isinstance(grandchild,list):result.add((expr[0],child[0],grandchild[0]))
            result|=paths3(child)
    return result
