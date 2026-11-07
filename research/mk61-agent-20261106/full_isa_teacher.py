"""Teacher wording with blinded executable full-program checks; train data only."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import collections
import hashlib
import json
import random
import re
import time
import urllib.request

from full_isa_common import ROOT,read,sha,write
from full_isa_vm import FullVM,check_task
from full_isa_protocol import decode
from tasks import save_jsonl
import teacher_data

teacher_data.URL='http://127.0.0.1:8001/v1/chat/completions'


def structured(root,kind,identity,messages,schema,*,tokens,temperature):
    path=root/'teacher-raw'/kind/(identity+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    payload={'model':teacher_data.MODEL,'messages':messages,'max_tokens':tokens,'temperature':temperature,
      'seed':int(hashlib.sha256(identity.encode()).hexdigest()[:7],16),'chat_template_kwargs':{'enable_thinking':False},
      'response_format':{'type':'json_schema','json_schema':{'name':'mk61_full_course','strict':True,'schema':schema}}}
    if path.exists():
        cached=json.loads(path.read_text());assert cached['request']==payload,'Teacher request changed'
        return json.loads(cached['response']['choices'][0]['message']['content'])
    last=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(teacher_data.URL,json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=120)as stream:response=json.load(stream)
            if response['choices'][0]['finish_reason']!='stop':raise ValueError('Truncated teacher response')
            value=json.loads(response['choices'][0]['message']['content'])
            write(path,{'request':payload,'response':response});return value
        except Exception as e:last=e;time.sleep(1)
    raise RuntimeError(str(last))


def parse_code(value):
    if isinstance(value,list)and value and all(type(x)is int and 0<=x<=255 for x in value):
        if len(value)>105:raise ValueError('Too long')
        return value
    if isinstance(value,str):
        value=value.strip()
        if '<write>'in value:return decode(value)
        words=value.split()
        if 1<=len(words)<=105 and all(re.fullmatch('[0-9A-Fa-f]{2}',x)for x in words):return [int(x,16)for x in words]
    raise ValueError('Invalid teacher program')


def main():
    out=ROOT/'teacher';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():print('Verified full ISA teacher data complete');return
    assert(ROOT/'data-frozen.json').exists()and(ROOT/'run-policy-frozen.json').exists()
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    assert all(sha(ROOT/n)==v for n,v in frozen['files'].items())
    rng=random.Random(6117050);rows=read(ROOT/'train.jsonl');selected=[]
    # Cover every documented opcode and every angle, then scientific/program
    # synthesis. Raw HEX-copy tasks are not treated as natural understanding.
    primitives=[r for r in rows if r['kind']=='primitive'and r['catalog_risk']=='documented'and':wording0'in r['id']]
    selected+=primitives
    for kind,n in [('numeric_synthesis',256),('programming',128),('interactive_game',16)]:
        pool=[r for r in rows if r['kind']==kind];rng.shuffle(pool);selected+=pool[:n]
    rng.shuffle(selected);write(out/'source-task-ids.json',[r['id']for r in selected]);started=time.monotonic();errors=[]
    def generate(row):
        identity=hashlib.sha256(row['id'].encode()).hexdigest()[:20]
        system=('Создай три разные русские формулировки одной задачи для программирования МК-61. '
          'Ответ только JSON объект с массивом texts. Сохрани точные операции, регистры, числовые константы, адреса, '
          'режим углов, порядок команд, изменение памяти, остановы и продолжение. Не добавляй новых действий. '
          'Не вставляй готовую программу HEX или числовой ответ. Не меняй названную инструкцию её аналогом. '
          'Пиши ясно и кратко: 12–75 слов. Для научных вычислений допустим естественный смысловой сюжет; '
          'для конкретной команды или раскладки программы сохраняй техническую точность. '
          'Все функции обычного МК-61 разрешены: тригонометрия, логарифмы, степени, BCD-логика, '
          'все регистры R0–RE, косвенная память, все циклы и подпрограммы. Не ограничивайся простой арифметикой. '
          'Не предлагай способы решения и дополнительные инструкции. Только переформулируй исходное условие. '
          'X — регистр стека, а R0 — отдельный регистр памяти. Никогда не подменяй X регистром R0.')
        user=json.dumps({'task':row['task'],'angle':row['angle']},ensure_ascii=False)
        schema={'type':'object','properties':{'texts':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'string','maxLength':700}}},'required':['texts'],'additionalProperties':False}
        value=structured(out,'wording-v2-no-hex',identity,[{'role':'system','content':system},{'role':'user','content':user}],schema,tokens=1800,temperature=.5)
        values=value.get('texts',[])
        result=[]
        for i,text in enumerate(values if isinstance(values,list)else[]):
            if not isinstance(text,str)or not 7<=len(text.split())<=90 or any(c in text for c in '<>`'):continue
            text=re.sub(r'Р([0-9A-E])',r'R\1',text).strip()
            if set(re.findall(r'\bR[0-9A-E]\b',text))!=set(re.findall(r'\bR[0-9A-E]\b',row['task'])):continue
            result.append({**row,'id':'teacher:'+identity+f':{i}','task':text,'source':'full_isa_teacher','original_task_id':row['id']})
        return result
    generated=[]
    with ThreadPoolExecutor(max_workers=8)as pool:
        futures={pool.submit(generate,r):r['id']for r in selected}
        for i,f in enumerate(as_completed(futures),1):
            try:generated+=f.result()
            except Exception as e:errors.append({'generation':futures[f],'error':str(e)[:200]})
            if i%24==0 or i==len(selected):write(out/'status.json',{'phase':'generation','jobs':i,'total':len(selected),'candidates':len(generated),'errors':len(errors)});print((out/'status.json').read_text(),flush=True)
    generated.sort(key=lambda r:r['id']);save_jsonl(out/'candidates.jsonl',generated);rng.shuffle(generated)
    batches=[generated[i:i+4]for i in range(0,len(generated),4)];decoded={}
    catalog=json.loads((ROOT/'catalog.json').read_text())
    table='\n'.join(r['hex']+' '+r['name']+(' (следующий байт — адрес)'if r['takes_address']else'')for r in catalog)
    def blind(index,batch):
        opaque={hashlib.sha256(('full-blind:'+r['id']).encode()).hexdigest()[:18]:r for r in batch}
        system=('Ты независимо пишешь программу обычного МК-61 только по условию и полному справочнику. Ответ JSON объект '
          'с массивом answers из объектов {"id":"...","code":"60 1C 50"}. code — полная программа HEX, не более 105 ячеек. '
          'Входы X/Y/Z/T/X1 и R0–RE уже содержат произвольные значения, кроме явно вводимых программой констант. '
          'Если задана одна инструкция и С/П, не добавляй другие операции. Сохраняй явно заданные адреса и память. '
          'Для тригонометрии соблюдай отдельно переданный режим углов. Поддерживай все команды МК-61, '
          'включая косвенные переходы и все L0–L3. Не заменяй команды с особыми эффектами похожей арифметикой. '
          'Если условие неполно, неоднозначно или невозможно, верни code=null. Соседние задачи независимы. '
          'X и R0 — РАЗНЫЕ регистры. Для sin(X) достаточно 1C 50; для sin(R0) нужно 60 1C 50. '
          'Не загружай R0, когда вход уже находится в X. Константы вводятся цифрами, точкой 0A и знаком 0B. '
          '24 вычисляет X^Y и сохраняет Y; 36/37/38/39 также не опускают стек. '
          'У прямых условий истина продолжает программу, ложь передаёт управление по следующему адресу. '
          'Циклы L0–L3 используют только R0–R3 и завершают уменьшение на единице. '
          'Пользуйся именно следующей таблицей, не придумывай коды:\n'+table)
        request=[{'id':key,'text':r['task'],'angle':r['angle']}for key,r in opaque.items()]
        identity=f'{index:04}-'+hashlib.sha256(json.dumps(request,ensure_ascii=False).encode()).hexdigest()[:16]
        item={'type':'object','properties':{'id':{'type':'string','enum':list(opaque)},'code':{'anyOf':[{'type':'null'},{'type':'string','pattern':'^[0-9A-F]{2}( [0-9A-F]{2}){0,104}$','maxLength':314}]}},'required':['id','code'],'additionalProperties':False}
        schema={'type':'object','properties':{'answers':{'type':'array','minItems':len(batch),'maxItems':len(batch),'items':item}},'required':['answers'],'additionalProperties':False}
        value=structured(out,'blind-program-v2-with-isa',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps(request,ensure_ascii=False)}],schema,tokens=2200,temperature=0)
        values=value.get('answers',[])
        result={x.get('id'):x.get('code')for x in values if isinstance(x,dict)}if isinstance(values,list)else{}
        return [(row,result.get(key))for key,row in opaque.items()]
    candidates=[]
    with ThreadPoolExecutor(max_workers=8)as pool:
        futures={pool.submit(blind,i,b):i for i,b in enumerate(batches)}
        for i,f in enumerate(as_completed(futures),1):
            try:candidates+=f.result()
            except Exception as e:errors.append({'blind':futures[f],'error':str(e)[:200]})
            if i%24==0 or i==len(batches):write(out/'status.json',{'phase':'blind_program_generation','batches':i,'total':len(batches),'decoded':len(candidates),'errors':len(errors)});print((out/'status.json').read_text(),flush=True)
    vm=FullVM();good=[];bad=[];forbidden={re.sub(r'\s+',' ',r['task'].lower())for name in ['validation.jsonl','audit.jsonl','closed-natural.jsonl']for r in read(ROOT/name)};seen=set()
    for i,(row,value)in enumerate(candidates):
        key=re.sub(r'\s+',' ',row['task'].lower())
        try:
            code=parse_code(value)
            from full_isa_protocol import linear_instructions
            candidate_ops={x['opcode']for x in linear_instructions(code)};reference_ops={x['opcode']for x in linear_instructions(row['reference_code'])}
            if not set(row['target_opcodes'])<=candidate_ops:raise ValueError('Named target instruction missing from blind program')
            flow={0x51,0x52,0x53,0x57,0x58,0x59,0x5A,0x5B,0x5C,0x5D,0x5E,*range(0x70,0xB0),*range(0xC0,0xD0),*range(0xE0,0xF0)}
            if candidate_ops&flow and not reference_ops&flow:raise ValueError('Unrequested control flow')
            if not check_task(vm,code,row)['pass']:raise ValueError('Blind program failed private core cases')
            if key in forbidden or key in seen:raise ValueError('Repeated/heldout wording')
            seen.add(key);good.append({**row,'blind_code':code,'semantic_check':'blind_teacher_program_executed_on_all_private_training_cases'})
        except (ValueError,TypeError,KeyError,ArithmeticError)as e:bad.append({'id':row['id'],'reason':str(e)})
        if i%100==0:write(out/'status.json',{'phase':'real_core_verification','checked':i,'total':len(candidates),'accepted':len(good)})
    good.sort(key=lambda r:r['id']);save_jsonl(out/'train.jsonl',good);save_jsonl(out/'rejected.jsonl',bad)
    manifest={'teacher':teacher_data.MODEL,'source_tasks':len(selected),'candidates':len(generated),'verified':len(good),'rejected':len(bad),
      'per_kind':dict(collections.Counter(r['kind']for r in good)),'errors':errors,'seconds':time.monotonic()-started,
      'all_labels_real_core_verified':True,'blind_checker_sees_reference_program':False,'same_model_two_independent_calls':True,
      'teacher_sees_new_audit':False,'training_sha256':sha(out/'train.jsonl'),'minimum_full_coverage_retained_by_canonical_course':True,
      'generation_sees_reference_hex':False,'blind_checker_has_complete_isa_reference':True,'bounded_structured_json':True}
    write(out/'manifest.json',manifest);write(out/'status.json',{'phase':'complete','verified':len(good)});print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
