"""User-proposed DeepSeek: action protocol and separate semantic translation.

No gradients. These are protocol diagnostics on already opened conditions.
The compiler hybrid is evaluated separately from autonomous agent DONE.
"""
import argparse
import ast
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request

import ar_run
import as_run
from ar_common import HERE, REPO, MODEL, read, write, sha
from ar_common import ROOT as FIRST
from ar_spec import infer, verify, equivalent, spec_text
from au_teacher import REFERENCE
from full_isa_math import compile_expr, UNARY, BINARY
from full_isa_vm import FullVM
from full_isa_protocol import REGISTERS
from ha_protocol import encode, parse_bytes, canonical

ROOT=REPO/'.build/mk61-agent-20261106/spec-diagnostic-deepseek-v1'
URL='http://127.0.0.1:18081/v1/chat/completions'
TEACHER='deepseek-ai/DeepSeek-V4.1-Flash'


def check_frozen():
    frozen=read(ROOT/'frozen.json')
    for name,digest in frozen['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in frozen['data'].items():assert sha(ROOT/name)==digest,name
    assert sha(MODEL/'model.mkqb')==frozen['small_packet_sha256']


class Teacher:
    def __init__(self):
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.cache=ROOT/'teacher-cache';self.cache.mkdir(exist_ok=True,parents=True)
        self.locks={};self.guard=threading.Lock()

    def request(self,messages,schema,name):
        payload={'model':TEACHER,'messages':messages,'temperature':0,'seed':260008,'max_tokens':512,
                 'chat_template_kwargs':{'thinking':False,'enable_thinking':False},
                 'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}}}
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode();key=hashlib.sha256(encoded).hexdigest()
        path=self.cache/(key+'.json')
        with self.guard:lock=self.locks.setdefault(key,threading.Lock())
        with lock:
            if path.exists():return read(path)
            started=time.monotonic()
            request=urllib.request.Request(URL,encoded,headers={'Content-Type':'application/json'})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request,timeout=150)as response:data=json.load(response)
                    break
                except Exception:
                    if attempt==2:raise
                    time.sleep(2)
            result={'payload':payload,'response':data,'seconds':time.monotonic()-started}
            write(path,result);return result

    def one(self,prompt,forced):
        schema={'type':'object','properties':{'action':{'type':'string','enum':[forced]if forced else['write','run','trace','done','unsure','diag']},
                'body':{'type':'string'}},'required':['action','body'],'additionalProperties':False}
        system=('You operate the MK-61 tool harness. Return one JSON action with action and body. '
                'body is space-separated HEX bytes; empty for done/trace/unsure. '
                'run has one test-index byte, diag has five bytes. write replaces the whole program and runs the current public case. '
                'There are no additional tools. Obey the Russian task and actual facts. '
                'DONE claims the original user task is solved.\n'+REFERENCE)
        cached=self.request([{'role':'system','content':system},{'role':'user','content':prompt}],schema,'mk61_action')
        data=cached['response'];content=data['choices'][0]['message'].get('content')or''
        try:
            result=json.loads(content);action=result['action'];body=parse_bytes(result['body'],empty=True)
            if forced and action!=forced:raise ValueError('FORCED_ACTION')
            generation={'action':action,'body':body,'codec_error':None}
        except (ValueError,KeyError,TypeError)as error:
            generation={'action':None,'body':[],'codec_error':str(error)}
        generation.update(raw=content,usage=data.get('usage'),finish_reason=data['choices'][0]['finish_reason'],seconds=cached['seconds'])
        return generation

    def generate(self,prompts,forced_action=None):
        return list(self.pool.map(lambda p:self.one(p,forced_action),prompts))


def power(a,b):
    if isinstance(b,dict)and b.get('constant')in ['0','1','2','4']:
        n=int(b['constant'])
        return {'constant':'1'}if n==0 else a if n==1 else ['square',a]if n==2 else ['square',['square',a]]
    return ['pow',a,b]


def parse_expression(text):
    """Only an arithmetic AST is accepted; never eval model-generated code."""
    tree=ast.parse(text,mode='eval')
    count=0
    def visit(node,depth=0):
        nonlocal count
        count+=1
        if count>64 or depth>12:raise ValueError('EXPRESSION_LIMIT')
        if isinstance(node,ast.Name):
            if node.id in [*REGISTERS,'X','Y','Z','T']:return node.id
            if node.id=='pi':return {'pi':True}
        elif isinstance(node,ast.Constant)and type(node.value)in [int,float]:
            return {'constant':canonical(node.value)}
        elif isinstance(node,ast.UnaryOp)and isinstance(node.op,ast.USub):return ['neg',visit(node.operand,depth+1)]
        elif isinstance(node,ast.BinOp):
            a,b=visit(node.left,depth+1),visit(node.right,depth+1)
            if isinstance(node.op,ast.Pow):return power(a,b)
            operators={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/'}
            if type(node.op)in operators:return [operators[type(node.op)],a,b]
        elif isinstance(node,ast.Call)and isinstance(node.func,ast.Name)and not node.keywords:
            op=node.func.id
            if op in UNARY and len(node.args)==1:return [op,visit(node.args[0],depth+1)]
            if op=='pow'and len(node.args)==2:return power(visit(node.args[0],depth+1),visit(node.args[1],depth+1))
        raise ValueError('UNSUPPORTED_EXPRESSION '+ast.dump(node)[:100])
    return visit(tree.body)


def prepare():
    assert not(ROOT/'frozen.json').exists()
    write(ROOT/'goals.json',read(FIRST/'goals.json'))
    policy=read(REPO/'.build/mk61-agent-20261106/spec-diagnostic-native-v1/policy.json')
    policy.update({'teacher':TEACHER,'endpoint':'known user DeepSeek service through temporary SSH forwarding',
                   'teacher_reference_provided':True,'teacher_thinking':False,
                   'additional_translation':'Russian to restricted arithmetic expression, no MK-61 HEX required',
                   'hybrid':'compile declared expression deterministically; audit against original task independently',
                   'new_final_test':False,'training_updates':0})
    write(ROOT/'policy.json',policy);(ROOT/'reference.txt').write_text(REFERENCE)
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not p.name.endswith(('_report.py','_remote.py'))}
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,
                             'data':{n:sha(ROOT/n)for n in ['goals.json','policy.json','reference.txt']},
                             'small_packet_sha256':sha(MODEL/'model.mkqb'),'model_outputs_seen_for_this_protocol':False,
                             'diagnostic_conditions_already_opened':True})
    print(json.dumps({'frozen':True,'teacher':TEACHER,'same_weights':True}))


def preflight():
    check_frozen();actor=Teacher();vm=FullVM();pool=['0','1','-1'];rows=[]
    for name,text,expr in [('square_R7','Вычисли квадрат R7, результат в X. Остальную память сохрани.', ['square','R7']),
                           ('subtract_R7_R8','Вычти R8 из R7, результат в X. Остальную память сохрани.', ['-','R7','R8'])]:
        view={'id':name,'task':text,'angle':'RAD','constants':pool,'public_tests':[]}
        prompt=as_run.goal_prompt(view,pool);g=actor.one(prompt,'write')
        result=verify(vm,g['body'],pool,{'X':expr,'writes':{},'angle':'RAD'},[{'R7':'2.25','R8':'-1.5'},{'R7':'-3.25','R8':'0.875'}])
        rows.append({'id':name,'generation':g,'ROM_check':result})
    write(ROOT/'preflight.json',rows);print(json.dumps(rows,ensure_ascii=False))
    assert all(not r['generation']['codec_error']for r in rows),'invalid API/format preflight'


def translate():
    check_frozen();goals=read(ROOT/'goals.json');actor=Teacher();vm=FullVM()
    schema={'type':'object','properties':{'X':{'type':'string'},'writes':{'type':'object','properties':{r:{'type':'string'}for r in REGISTERS},'additionalProperties':False},
            'angle':{'type':'string','enum':['RAD','DEG','GRAD']}},'required':['X','writes','angle'],'additionalProperties':False}
    system=('Переведи русское условие в формальную спецификацию результата. Не пиши код МК-61. '
            'Верни JSON: X — выражение от ИСХОДНЫХ регистров, writes — только явно требуемые изменения памяти (пустой объект, если их нет), angle — режим углов. '
            'Все неназванные регистры должны сохраниться. Выражения: имена R0..RE, десятичные константы, pi, скобки, +,-,*,/,**; '
            'функции sin,cos,tan,asin,acos,atan,sqrt,square,abs,neg,reciprocal,exp,pow10,ln,log10,int,frac,sign. '
            'int отсекает к нулю, frac сохраняет знак. sin/cos/tan и обратные функции используют angle. '
            'Не добавляй шаги реализации или временные регистры. Выражай конечные значения через исходные входы.')
    def one(goal):
        user='Режим: '+goal['angle']+'.\nЗадача: '+goal['task']
        return actor.request([{'role':'system','content':system},{'role':'user','content':user}],schema,'postcondition')
    rows=[]
    for at in range(0,len(goals),4):
        chunk=goals[at:at+4];answers=list(actor.pool.map(one,chunk))
        for goal,cached in zip(chunk,answers):
            response=cached['response'];raw=response['choices'][0]['message'].get('content')or''
            spec=None;error=None;body=[]
            try:
                answer=json.loads(raw);spec={'X':parse_expression(answer['X']),'writes':{r:parse_expression(x)for r,x in answer['writes'].items()},'angle':answer['angle']}
                if set(spec['writes'])-set(REGISTERS):raise ValueError('UNKNOWN_REGISTER')
                intent=equivalent(spec,goal['spec'],goal['audit_inputs'])
                if any(x!=spec['X']for x in spec['writes'].values()):raise ValueError('HYBRID_MULTIRESULT_UNSUPPORTED')
                rawcode=compile_expr(spec['X'])+[0x40+int(r[1:],16)for r in spec['writes']]+[0x50]
                body=encode(rawcode,goal['pool'],'asm')
                implementation=verify(vm,body,goal['pool'],spec,goal['audit_inputs'])
                task=verify(vm,body,goal['pool'],goal['spec'],goal['audit_inputs'])
            except (ValueError,ArithmeticError,KeyError,TypeError,RuntimeError)as e:
                error=str(e);intent=equivalent(spec,goal['spec'],goal['audit_inputs']);implementation={'status':'UNKNOWN'};task={'status':'UNKNOWN'}
            rows.append({'id':goal['id'],'task':goal['task'],'raw':raw,'spec':spec,'intent':intent,'body':body,
                         'implementation_audit':implementation,'task_audit':task,'error':error,'usage':response.get('usage'),
                         'finish_reason':response['choices'][0]['finish_reason']})
        write(ROOT/'translation-status.json',{'completed':len(rows),'total':32})
        print(json.dumps({'translated':len(rows),'correct_intent':sum(r['intent']['tested_equal']for r in rows)}),flush=True)
    write(ROOT/'translation.json',{'teacher':TEACHER,'records':rows,'training_updates':0,'compiler_hybrid_not_autonomous_DONE':True})
    check_frozen()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','preflight','run','translate']);a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='preflight':preflight()
    elif a.action=='translate':translate()
    else:
        ar_run.ROOT=ROOT;ar_run.check_frozen=check_frozen;ar_run.Teacher=Teacher;ar_run.run('teacher')


if __name__=='__main__':main()
