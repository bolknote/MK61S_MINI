"""DeepSeek wording plus independent reverse translation, no teacher DONE labels."""
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request
from ay_common import ROOT,TEACHER,URL,rows,write,save_rows,read,sha
from ay_data import CONSTANTS
from ay_codec import compile_spec,encode
from ar_spec import expression_text,equivalent,verify
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from ha_protocol import constants,canonical
from av_deepseek import parse_expression


class Client:
    def __init__(self):
        self.cache=ROOT/'teacher-cache';self.cache.mkdir(parents=True,exist_ok=True)
        self.locks={};self.guard=threading.Lock();self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def call(self,system,user,schema,name):
        payload={'model':TEACHER,'temperature':0,'seed':26110802,'max_tokens':3500,
                 'chat_template_kwargs':{'thinking':False,'enable_thinking':False},
                 'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(user,ensure_ascii=False)}],
                 'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}}}
        data=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode();key=hashlib.sha256(data).hexdigest();path=self.cache/(key+'.json')
        with self.guard:lock=self.locks.setdefault(key,threading.Lock())
        with lock:
            if path.exists():return read(path)
            started=time.monotonic();request=urllib.request.Request(URL,data,headers={'Content-Type':'application/json'})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request,timeout=180)as response:result=json.load(response)
                    break
                except Exception:
                    if attempt==2:raise
                    time.sleep(2)
            value={'payload':payload,'response':result,'seconds':time.monotonic()-started}
            write(path,value);return value


def pool_for(text):
    pool=['0','1','-1']
    for x in [*CONSTANTS,*constants(text)]:
        x=canonical(x)
        if x not in pool:pool.append(x)
    return pool


def task_text(question,spec):
    question=question.strip()
    if not 8<=len(question)<=350:raise ValueError('QUESTION_LENGTH')
    text=question+' Результат оставь в X. '
    for r in spec['writes']:text+='Тот же результат запиши в '+r+'. '
    return text+'Остальные регистры памяти сохрани; после вычисления остановись.'


def wordings(client,chunk,attempt):
    schema={'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':{
        'id':{'type':'string'},'questions':{'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2}},
        'required':['id','questions'],'additionalProperties':False}}},'required':['items'],'additionalProperties':False}
    system=('Ты создаёшь точные русские задания по формальным выражениям. Для каждого id дай две разные короткие естественные формулировки '
      'только вычисляемого выражения, до 220 символов каждая. Сохраняй порядок вычитания/деления, вложенность, аргументы и числовые константы. '
      'Регистры называй ровно R0..RE, числа пиши цифрами. Не добавляй входы, числа или операции. Не пиши HEX, код, JSON внутри формулировок, '
      'английские имена функций или общую инструкцию писать программу. Не употребляй неопределённое «это» вместо явного аргумента. '
      'Память, останов и место результата добавит harness. Углы берутся из поля angle; обратные функции выдают число в том же режиме. '
      'int означает отсечение к нулю, frac — дробную часть с исходным знаком, sign — -1 для отрицательных и +1 для остальных. '
      'В ответе только JSON items; верни все id без переименования.')
    user={'attempt':attempt,'expressions':[{'id':g['id'],'X':expression_text(g['spec']['X']),'angle':g['spec']['angle']}for g in chunk]}
    result=client.call(system,user,schema,'ay_wordings')
    try:
        text=result['response']['choices'][0]['message'].get('content')or'';items=json.loads(text)['items']
        return {x['id']:x['questions']for x in items}
    except (ValueError,KeyError,TypeError):return {}


def reverse(client,items):
    schema={'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':{
       'id':{'type':'string'},'X':{'type':'string'},'angle':{'type':'string','enum':['RAD','DEG','GRAD']},
       'writes':{'type':'object','properties':{r:{'type':'string'}for r in REGISTERS},'additionalProperties':False}},
       'required':['id','X','angle','writes'],'additionalProperties':False}}},'required':['items'],'additionalProperties':False}
    system=('Переведи каждое русское условие в формальную спецификацию. Верни все id и JSON items: X — выражение через ИСХОДНЫЕ регистры; '
       'writes — только явно требуемые конечные изменения памяти; angle — данный режим. Не пиши код МК-61, не создавай временные регистры. '
       'Выражения: R0..RE, десятичные числа, pi, скобки,+,-,*,/,**; функции sin,cos,tan,asin,acos,atan,sqrt,square,abs,neg,reciprocal,'
       'exp,pow10,ln,log10,int,frac,sign. int отсекает к нулю; frac сохраняет знак; sign(0)=1. Угловые функции используют angle. '
       'Все неназванные регистры остаются неизменными. Не подгоняй ответы по соседним примерам.')
    result=client.call(system,items,schema,'ay_reverse')
    try:
        text=result['response']['choices'][0]['message'].get('content')or''
        return {x['id']:x for x in json.loads(text)['items']}
    except (ValueError,KeyError,TypeError):return {}


def prepare_chunk(client,chunk):
    accepted={g['id']:[]for g in chunk};audit=[]
    for attempt in range(3):
        todo=[g for g in chunk if len(accepted[g['id']])<(2 if g['split']=='train'else 1)]
        if not todo:break
        generated=wordings(client,todo,attempt);candidates=[];lookup={}
        for g in todo:
            questions=generated.get(g['id'],[])
            for i,q in enumerate(questions[:2]):
                try:text=task_text(q,g['spec'])
                except (ValueError,TypeError):continue
                identifier=g['id']+f':a{attempt}:p{i}'
                if any(x['task']==text for x in accepted[g['id']]):continue
                candidates.append({'id':identifier,'task':text,'angle':g['spec']['angle']});lookup[identifier]=(g,text)
        if not candidates:continue
        # The reverse request contains only Russian tasks and angle, no source AST.
        verified={}
        for at in range(0,len(candidates),8):verified.update(reverse(client,candidates[at:at+8]))
        for item in candidates:
            g,text=lookup[item['id']];v=verified.get(item['id']);ok=False;error=None
            try:
                if v is None:raise ValueError('REVERSE_MISSING')
                spec={'X':parse_expression(v['X']),'writes':{r:parse_expression(x)for r,x in v['writes'].items()},'angle':v['angle']}
                if set(spec['writes'])-set(REGISTERS):raise ValueError('REGISTER')
                ok=equivalent(spec,g['spec'],g['checker_inputs']+g['audit_inputs'])['tested_equal']
            except (ValueError,KeyError,ArithmeticError,TypeError)as e:error=str(e)
            audit.append({'id':item['id'],'task':text,'verified':bool(ok),'reverse':v,'error':error})
            needed=2 if g['split']=='train'else 1
            if ok and len(accepted[g['id']])<needed:
                pool=pool_for(text)
                try:body=compile_spec(g['spec'],pool);spec_body=encode(g['spec'],pool)
                except (ValueError,ArithmeticError):continue
                accepted[g['id']].append({**g,'task':text,'pool':pool,'reference_body':body,'spec_body':spec_body,
                                         'paraphrase':len(accepted[g['id']]),'teacher_reverse_verified':True})
    return accepted,audit


def main():
    assert not(ROOT/'frozen.json').exists()
    bank=read(ROOT/'ast-frozen.json')
    for n,d in bank['files'].items():assert sha(ROOT/n)==d,n
    if(ROOT/'teacher-frozen.json').exists():print('Teacher corpus already frozen');return
    client=Client();groups=[g for split in ['train','development','closed']for g in rows(ROOT/(split+'-asts.jsonl'))]
    output={s:[]for s in ['train','development','closed']};audit=[];processed=0;started=time.monotonic()
    chunks=[groups[at:at+6]for at in range(0,len(groups),6)]
    # Request orchestration has four independent tasks; each uses synchronous HTTP.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
        pending={pool.submit(prepare_chunk,client,c):c for c in chunks}
        for f in concurrent.futures.as_completed(pending):
            accepted,checks=f.result();audit.extend(checks)
            for group in pending[f]:
                variants=accepted[group['id']]
                if len(variants)==(2 if group['split']=='train'else 1):output[group['split']].extend(variants)
            processed+=len(pending[f])
            if processed%30==0 or processed==len(groups):
                write(ROOT/'teacher-status.json',{'phase':'DeepSeek_wording_and_independent_reverse','ASTs_processed':processed,'ASTs_total':len(groups),
                     'rows':{s:len(v)for s,v in output.items()},'seconds':time.monotonic()-started})
                print(json.dumps({'teacher_ASTs':processed,'total':len(groups),'rows':{s:len(v)for s,v in output.items()},'seconds':round(time.monotonic()-started,1)}),flush=True)
    vm=FullVM();ROM_cases=0
    for split,values in output.items():
        # Scheduling never determines dataset order or training sample order.
        values.sort(key=lambda g:(g['id'],g['paraphrase']))
        for g in values:
            result=verify(vm,g['reference_body'],g['pool'],g['spec'],g['public_inputs']+g['audit_inputs'])
            assert result['status']=='TESTED',(g['id'],result);ROM_cases+=result['cases']
        assert len(values)>={'train':2560,'development':150,'closed':250}[split],(split,len(values))
        save_rows(ROOT/(split+'-goals.jsonl'),values)
    save_rows(ROOT/'teacher-reverse-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'teacher':TEACHER,'files':{s+'-goals.jsonl':sha(ROOT/(s+'-goals.jsonl'))for s in output},
                  'sizes':{s:len(v)for s,v in output.items()},'reverse_requests_never_contained_source_AST':True,
                  'verified_ROM_cases':ROM_cases,'audit_sha256':sha(ROOT/'teacher-reverse-audit.jsonl'),
                  'no_LLM_DONE_truth_labels':True,'seconds':time.monotonic()-started})
    print(json.dumps({'teacher_corpus_complete':True,'rows':{s:len(v)for s,v in output.items()},'ROM_cases':ROM_cases}),flush=True)


if __name__=='__main__':main()
