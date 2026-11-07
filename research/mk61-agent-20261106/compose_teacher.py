"""New multi-operation Russian minimal pairs, verified with blinded opaque IDs."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import collections
import hashlib
import json
import random
import re
import time

from compose_common import ROOT,read,opcount,stack_depth,make_task
from course_common import ARITY,canonical,parse_prefix,prefix
from course_teacher import normalize,no_side_effects
from tasks import random_expr,registers_used,save_jsonl,split_of,expression_text
from teacher_data import call,MODEL

STYLES=[
 'Разговорная просьба. Одно условие через смысл величин, другое с прямыми названиями действий.',
 'Короткая практическая история: расходы, запасы, измерения, материалы. Порядок упоминания регистров меняй.',
 'Игровое правило: начисление, штраф, координаты, движение, делёж ресурсов. Условие самодостаточно.',
 'Сжатая запись величин через обозначения регистров и вопрос в конце. Избегай начала В регистре хранится.',
 'Задача из учебной тетради. Разные синтаксические конструкции; естественный русский язык.',
 'Алгоритмическая инструкция словами с явно указанным порядком действий, без формулы и готового решения.'
]


def jobs():
    rng=random.Random(6112801);out=[]
    for split,count in [('train',384),('validation',48),('test',48)]:
        for i in range(count):
            level=2 if i%2==0 else 3
            for attempt in range(10000):
                expr=random_expr(rng,3)
                if isinstance(expr,str)or opcount(expr)!=level or stack_depth(expr)>4 or len(registers_used(expr))<2:continue
                if split_of(expr)!=split:continue
                others=[op for op in ARITY if ARITY[op]==ARITY[expr[0]]and op!=expr[0]];rng.shuffle(others)
                alternate=next(([op,*expr[1:]]for op in others if split_of([op,*expr[1:]])==split),None)
                if alternate is not None or split!='train':
                    try:
                        make_task('',expr,random.Random(6112810+i),'probe',split=split)
                        if alternate:make_task('',alternate,random.Random(6112820+i),'probe',split=split)
                    except ValueError:continue
                    break
            else:raise ValueError('Cannot fill structural split')
            out.append({'id':f'{split}:{i}','split':split,'level':level,'exprs':[expr]+([alternate]if alternate else[]),'style':i%len(STYLES)})
    # Elementary language families are assigned by complete jobs, not individual paraphrases.
    for i in range(126):
        op=list(ARITY)[i%7];names=rng.sample(['R0','R1','R2','R3'],2);expr=[op,*names[:ARITY[op]]]
        alternate=rng.choice([x for x in ARITY if ARITY[x]==ARITY[op]and x!=op]);other=[alternate,*expr[1:]]
        split='validation'if i%9==0 else'test'if i%9==1 else'train'
        out.append({'id':f'simple:{i}','split':split,'level':1,'exprs':[expr,other],'style':i%len(STYLES)})
    rng.shuffle(out);return out


def main():
    root=ROOT/'teacher';root.mkdir(parents=True,exist_ok=True)
    if(root/'manifest.json').exists():print('Verified teacher data complete');return
    assert(ROOT/'frozen.json').exists()
    started=time.monotonic();generated=[];errors=[];work=jobs()
    def generate(job):
        system=('Составь ровно четыре разных русских условия для одного заданного арифметического выражения. '
          'Ответ только JSON-массив из четырёх строк, без объектов и служебных id. '
          'Каждое условие самостоятельно задаёт ровно полученное выражение и только его. По12-55 слов. '
          'Используй R0,R1,R2,R3 как исходные числа; объясни роли всех нужных регистров. '
          'Все входы только читаются, результат нужен в X. Не требуй записывать в исходные регистры. '
          'Не добавляй константы, округление, сравнения, условные действия или лишние вычисления. '
          'Не пиши формулу, выражение в скобках, программу HEX, пример чисел или готовый ответ. '
          'Смысл и порядок некоммутативных действий должны быть точными. Не делай одинаковые истории для всех четырёх вариантов. '
          'Величины могут быть подписанными; модуль, смену знака и квадрат различай явно.')
        result=[]
        for k,expr in enumerate(job['exprs']):
            identity=hashlib.sha256((job['id']+':'+str(k)).encode()).hexdigest()[:20]
            response=call(root,'generate-expression-v2',identity,
              [{'role':'system','content':system},{'role':'user','content':STYLES[job['style']]+'\nВыражение: '+expression_text(expr)+
                '\nДерево операций: '+json.dumps(expr,ensure_ascii=False)}],tokens=1600,temperature=.4)
            for n,text in enumerate(response if isinstance(response,list)else[]):
                if not isinstance(text,str):continue
                text=re.sub(r'Р([0-3])',r'R\1',text).strip()
                if not 8<=len(text.split())<=75 or any(c in text for c in '<>=`')or not no_side_effects(text):continue
                if set(re.findall(r'R[0-9A-F]',text))!=registers_used(expr):continue
                result.append({'id':'compose-teacher:'+job['id']+':'+identity+':'+str(n),
                  'text':text,'expression':expr,'split':job['split'],'level':job['level'],
                  'pair_id':job['id']+':'+str(n),'language_family':job['id'],'style':job['style']})
        return result
    with ThreadPoolExecutor(max_workers=4)as pool:
        futures=[pool.submit(generate,job)for job in work]
        for n,f in enumerate(as_completed(futures),1):
            try:generated+=f.result()
            except Exception as e:errors.append({'generate':str(e)[:200]})
            if n%10==0 or n==len(work):
                status={'phase':'generation','jobs':n,'total':len(work),'rows':len(generated),'errors':len(errors)}
                (root/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    generated.sort(key=lambda r:r['id']);save_jsonl(root/'candidates.jsonl',generated)
    random.Random(6112802).shuffle(generated);batches=[generated[i:i+12]for i in range(0,len(generated),12)]
    def verify(i,batch):
        opaque={hashlib.sha256(('compose-blind:'+r['id']).encode()).hexdigest()[:20]:r for r in batch}
        system=('Независимо восстанови алгоритм по русскому условию. Ответ JSON-массив '
          '{"id":"...","prefix":"..."}. Префикс: операция перед аргументами, без скобок. '
          'Операции + - * / abs neg square; первые четыре имеют два аргумента, остальные один. '
          'Листья R0,R1,R2,R3. Верни null при неоднозначности, лишних числах, неполных ролях, '
          'неподдерживаемых действиях или требовании писать результат в исходный регистр. '
          'Соседние строки независимы, не угадывай алгоритм по соседним строкам.')
        identity=str(i)+'-'+hashlib.sha256(json.dumps(batch,ensure_ascii=False).encode()).hexdigest()[:12]
        response=call(root,'blind',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':key,'text':r['text']}for key,r in opaque.items()],ensure_ascii=False)}],tokens=2200,temperature=0)
        decoded={r.get('id'):r.get('prefix')for r in response if isinstance(r,dict)}
        result=[]
        for key,row in opaque.items():
            try:valid=canonical(parse_prefix(decoded.get(key,'')))==canonical(row['expression'])
            except (ValueError,TypeError,AttributeError):valid=False
            if valid:result.append(row)
        return result
    good=[]
    with ThreadPoolExecutor(max_workers=4)as pool:
        futures=[pool.submit(verify,i,batch)for i,batch in enumerate(batches)]
        for n,f in enumerate(as_completed(futures),1):
            try:good+=f.result()
            except Exception as e:errors.append({'verify':str(e)[:200]})
            if n%10==0 or n==len(batches):
                status={'phase':'blind_verification','batches':n,'total':len(batches),'retained':len(good),'errors':len(errors)}
                (root/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    forbidden={normalize(x['task'])for p in ROOT.glob('*.jsonl')for x in read(p)}
    bykey=collections.defaultdict(list)
    for row in good:bykey[normalize(row['text'])].append(row)
    partitions={};dropped=collections.Counter()
    for split in ['train','validation','test']:
        values=[]
        for key,pool in bykey.items():
            if key in forbidden:dropped['manual_exact_overlap']+=1;continue
            if len({r['split']for r in pool})!=1:dropped['cross_split_wording']+=1;continue
            row=pool[0]
            if row['split']==split:values.append(row)
        values.sort(key=lambda r:r['id']);save_jsonl(root/(split+'.jsonl'),values);partitions[split]=len(values)
    if partitions['train']<2200:raise ValueError('Insufficient independently verified teacher data')
    report={'teacher':MODEL,'partitions':partitions,'generated':len(generated),'verified':len(good),
      'dropped':dict(dropped),'errors':errors,'seconds':time.monotonic()-started,
      'fresh_conditions_sent_to_teacher':False,'checker_sees_target_expression':False,
      'structural_train_split_for_multioperation':True,'language_pairs_grouped':True}
    (root/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (root/'status.json').write_text(json.dumps({'phase':'complete','partitions':partitions})+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
