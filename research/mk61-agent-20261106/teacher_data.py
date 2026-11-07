"""Collect Russian paraphrases, then blind-check their semantics using the local teacher."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import re
import time
import urllib.request

from tasks import BUILD, compile_expr, expression_text, family_of, random_expr, save_jsonl, split_of

MODEL="Qwen/Qwen3.8-Flash-Next-FP8"
URL="http://127.0.0.1:8000/v1/chat/completions"
STYLES=[
    "Короткая естественная просьба обычного пользователя. Разные глаголы и порядки слов.",
    "Игровая механика: очки, координаты, штрафы, заряды, движение, ресурсы. Не добавляй действий к формуле.",
    "Практический сюжет: покупки, измерения, количество, путь. Объясни связь величин через смысл, без словесного копирования формулы.",
    "Описание алгоритма или небольшая задача из учебника. Меняй порядок упоминания регистров и способ описания операций."
]


def canonical(expr):
    # Both common JSON AST serializations describe the same whitelisted grammar.
    # Converting {op,args} changes only representation, never the expression.
    if isinstance(expr,dict) and set(expr)=={'op','args'} and isinstance(expr['args'],list):
        expr=[expr['op'],*expr['args']]
    if isinstance(expr,str):
        if re.fullmatch(r"R[0-3]",expr):return expr
        raise ValueError("Unknown register")
    if not isinstance(expr,list) or not expr:raise ValueError("Not an expression")
    op,*xs=expr
    if op not in ['+','-','*','/','abs','neg','square'] or len(xs)!=(1 if op in ['abs','neg','square'] else 2):
        raise ValueError("Invalid AST")
    children=[canonical(x) for x in xs]
    if op in ['+','*']:children.sort()
    return op+'('+','.join(children)+')'


def decode(text):
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
    return json.loads(text)


def call(root,kind,identity,messages,*,tokens=1800,temperature=.7):
    path=root/'teacher-raw'/kind/(identity+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return decode(json.loads(path.read_text())["response"]["choices"][0]["message"]["content"])
    payload={"model":MODEL,"messages":messages,"temperature":temperature,"max_tokens":tokens,
             "seed":int(hashlib.sha256(identity.encode()).hexdigest()[:7],16),
             "chat_template_kwargs":{"enable_thinking":False}}
    last=None
    for attempt in range(4):
        try:
            req=urllib.request.Request(URL,json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as stream:response=json.load(stream)
            value=decode(response["choices"][0]["message"]["content"])
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({"request":payload,"response":response},ensure_ascii=False)+'\n');tmp.replace(path)
            return value
        except Exception as error:
            last=error
            # Sleep only on this detached worker; root conversation remains responsive.
            time.sleep(min(8,1+attempt*2))
    raise RuntimeError(str(last))


def templates():
    rng=random.Random(6110602)
    exprs=[[op,'R0','R1'] for op in ['+','-','*','/']]+[[op,'R0'] for op in ['abs','neg','square']]
    exprs += [
        ['+',['+','R0','R1'],'R2'],['-',['+','R0','R1'],'R2'],
        ['+','R0',['*','R1','R2']],['-','R0',['*','R1','R2']],
        ['/',['+','R0','R1'],'R2'],['*',['+','R0','R1'],'R2'],
        ['abs',['-','R0','R1']],['abs',['+','R0','R1']],
        ['neg',['+','R0','R1']],['square',['-','R0','R1']],
        ['+',['square','R0'],'R1'],['-',['square','R0'],'R1'],
        ['+',['*','R0','R1'],['*','R2','R3']],
        ['-',['*','R0','R1'],['*','R2','R3']],
        ['+',['abs','R0'],['abs','R1']],['-',['abs','R0'],['abs','R1']],
    ]
    exprs=[e for e in exprs if split_of(e)=='train']
    seen={canonical(e) for e in exprs}
    while len(exprs)<88:
        e=random_expr(rng,rng.choice([1,2,2,3]))
        if isinstance(e,str) or split_of(e)!='train' or len(compile_expr(e))>11:continue
        key=canonical(e)
        if key in seen:continue
        exprs.append(e);seen.add(key)
    return exprs


def generate(args):
    root=args.root;root.mkdir(parents=True,exist_ok=True)
    if (root/'teacher-manifest.json').exists():raise SystemExit('Teacher data already complete')
    started=time.monotonic()
    jobs=[(i,e,s) for i,e in enumerate(templates()) for s in range(len(STYLES))]
    def worker(job):
        i,expr,style=job
        system=("Ты создаёшь качественные русские условия задач для обучения крошечной модели программированию МК-61. "
                "Ответ — только JSON-массив из 8 объектов с полями text и expr. expr — дерево выражения JSON: "
                "операторы +,-,*,/,abs,neg,square; листья R0,R1,R2,R3. text — естественное русское условие, "
                "не более 55 слов; оно точно задаёт требуемое выражение. Вход уже в названных регистрах. "
                "Не пиши формулу, байты программы, решение, ответ или примеры чисел в text. "
                "Назови роль каждого нужного регистра. Не вводи новые константы, действия или округление. "
                "Результат нужен только в X. Регистры R0-R3 только читаются: никогда не требуй записывать или сохранять ответ в них. "
                "Простые операции формулируй разнообразно. Под сложную формулу не выдумывай бессмысленный сюжет. "
                "expr должно точно совпадать с заданным деревом, но text не должно пересказывать его одним шаблоном.")
        user=STYLES[style]+"\nЗаданный алгоритм: "+json.dumps(expr,ensure_ascii=False)+"\nНапиши восемь разных условий."
        values=call(root,'generate',f'{i:03}-{style}',[{'role':'system','content':system},{'role':'user','content':user}],tokens=2600)
        accepted=[]
        for j,item in enumerate(values if isinstance(values,list) else []):
            try:
                text=item['text'].strip()
                if canonical(item['expr'])!=canonical(expr):continue
                if not 5<=len(text.split())<=65 or not re.search('[а-яА-ЯёЁ]',text):continue
                if any(x in text for x in ['<','>','X =','X=','```']):continue
                accepted.append({'id':f'teacher:{i:03}:{style}:{j}','text':text,'expression':expr,'family':family_of(expr),
                                 'teacher':MODEL,'raw_source':f'generate/{i:03}-{style}.json','style':style,'template':i})
            except (KeyError,ValueError,TypeError):continue
        return accepted
    rows=[];errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(worker,j):j for j in jobs}
        for n,f in enumerate(as_completed(futures),1):
            try:rows+=f.result()
            except Exception as e:errors.append({'job':futures[f][0::2],'error':str(e)[:250]})
            if n%8==0 or n==len(jobs):
                (root/'generation-status.json').write_text(json.dumps({'done':n,'total':len(jobs),'accepted_before_semantic_check':len(rows),'errors':len(errors),'seconds':time.monotonic()-started})+'\n')
                print((root/'generation-status.json').read_text(),flush=True)
    rows=list({re.sub(r'\s+',' ',r['text'].lower()):r for r in rows}.values());rows.sort(key=lambda r:r['id'])
    save_jsonl(root/'teacher-candidates.jsonl',rows)
    # The checker sees the text and register grammar, never the intended expression.
    batches=[rows[i:i+12] for i in range(0,len(rows),12)]
    def check_worker(pair):
        index,batch=pair
        system=("Проверь смысл русских арифметических задач. Верни только JSON-массив объектов с id и expr. "
                "По каждому text самостоятельно выведи дерево операции. Дерево: [оператор,аргумент,...], "
                "операторы +,-,*,/,abs,neg,square; листья — строки R0,R1,R2,R3. У abs,neg,square один аргумент, "
                "у остальных два. neg означает противоположное число. Если условие неоднозначное, неполное или "
                "не укладывается в грамматику, верни expr=null. Не выдумывай отсутствующие регистры или действия.")
        identity=f'{index:04}-'+hashlib.sha256(json.dumps(batch,ensure_ascii=False).encode()).hexdigest()[:12]
        values=call(root,'verify',identity,[{'role':'system','content':system},
                     {'role':'user','content':json.dumps([{'id':r['id'],'text':r['text']} for r in batch],ensure_ascii=False)}],tokens=2000,temperature=0)
        lookup={x['id']:x.get('expr') for x in values if isinstance(x,dict) and 'id'in x}
        good=[];rejected=[]
        for row in batch:
            try:match=canonical(lookup.get(row['id']))==canonical(row['expression'])
            except (ValueError,TypeError):match=False
            if match:good.append({**row,'semantic_check':'blind_teacher_exact_AST_modulo_commutativity'})
            else:rejected.append({'id':row['id'],'text':row['text'],'expected':row['expression'],'parsed':lookup.get(row['id'])})
        return good,rejected
    good=[];rejected=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(check_worker,p):p[0] for p in enumerate(batches)}
        for n,f in enumerate(as_completed(futures),1):
            try:
                g,r=f.result();good+=g;rejected+=r
            except Exception as e:errors.append({'verify_batch':futures[f],'error':str(e)[:250]})
            if n%8==0 or n==len(batches):
                (root/'verification-status.json').write_text(json.dumps({'done':n,'total':len(batches),'verified':len(good),'rejected':len(rejected),'errors':len(errors),'seconds':time.monotonic()-started})+'\n')
                print((root/'verification-status.json').read_text(),flush=True)
    good.sort(key=lambda r:r['id']);save_jsonl(root/'teacher-verified.jsonl',good);save_jsonl(root/'teacher-rejected.jsonl',rejected)
    manifest={'teacher':MODEL,'endpoint':URL,'templates':len(templates()),'candidates':len(rows),'verified':len(good),
              'rejected':len(rejected),'errors':errors,'seconds':time.monotonic()-started,
              'sha256':hashlib.sha256((root/'teacher-verified.jsonl').read_bytes()).hexdigest(),
              'fresh_test_seen_by_teacher':False,'checker_blinded_to_target_expression':True,
              'limitations':'Two passes of the same teacher are a semantic filter, not a human proof; bytecode references are separately executed on microcode core.'}
    (root/'teacher-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)
    if len(good)<1200:raise ValueError('Insufficient verified linguistic variety')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=BUILD/'distill-v1');p.add_argument('--workers',type=int,default=4)
    generate(p.parse_args())
