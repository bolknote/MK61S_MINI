"""Balanced teacher minimal pairs, blind semantic checks and whole language families."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import time

from course_common import ARITY,canonical,parse_prefix,prefix
from tasks import BUILD,save_jsonl
from teacher_data import call,MODEL

STYLES=[
 'Естественная разговорная просьба. Без канцелярских оборотов. Меняй первые слова предложений.',
 'Короткая история с вопросом в конце. Объясни роли величин, не называй математическую операцию напрямую, если смысл ясен.',
 'Одна точная инструкция. Сначала желаемый результат, потом пояснение входных величин.',
 'Условие из учебной книги или игровой инструкции. Пиши просто и однозначно.',
 'Два коротких предложения: описание величин и просьба получить результат. Меняй порядок упоминания регистров.',
 'Пользователь объясняет своими словами. Используй разные синонимы действий и разные грамматические конструкции.'
]
TOPICS={
 '+':'очки двух этапов;массы двух деталей;два участка пути;общая сумма взносов;премия к счёту;поправка к показанию;люди в двух группах;два объёма жидкости;время двух операций;две партии товара;длины двух отрезков;расход двух материалов;приход двух ресурсов;два платежа;две группы мест;книги на двух полках;листы для двух целей;монеты двух видов;суммарный выигрыш;заряды двух аккумуляторов;данные двух счётчиков;составная длина провода;общее количество жетонов;два слагаемых абстрактного расчёта',
 '-':'остаток ресурса;штраф к счёту;денежная сдача;неиспользованные попытки;остаток листов;долг после платежа;оставшийся заряд;разность двух показаний;израсходованное топливо;разница набранных очков;непроданные товары;оставшееся расстояние;свободные места;невыполненная часть плана;оставшиеся монеты;разность двух длин;расход запаса;нужная поправка;разница цен;оставшееся время;вклад после снятия;запас деталей;чистый доход после расхода;уменьшение абстрактной величины',
 '*':'цена и количество;площадь прямоугольника;скорость и время;очки за ход и ходы;масса элемента и количество;ряды и места в ряду;ящики и детали в ящике;наборы и предметы в наборе;частота и время;расход в единицу времени;равномерный приток жидкости;масштабный коэффициент;пачки и листы;одинаковые покупки;плата за час и часы;высота и ширина поля;равные партии товара;жетоны за этап и этапы;ёмкость сосуда и сосуды;полки и книги на полке;постоянная норма и число повторов;билеты и цена билета;длина секции и число секций;два множителя абстрактного расчёта',
 '/':'равные доли;цена одной покупки;средняя скорость;масса одного изделия;длина одного куска;награда одному участнику;порции жидкости без округления;количество за единицу времени;отношение двух величин;ресурс на одного получателя;цена одной детали;средний результат за ход;длина за единицу времени;объём одной ёмкости;масса единицы товара;расход на один этап;равное распределение очков;сколько раз одна величина больше;общая сумма и число частей;общее количество и норма на группу;площадь на одну секцию;вес одного набора;длительность одного равного этапа;делимое и делитель абстрактного расчёта',
 'abs':'подписанное отклонение;расстояние точки до нуля;направленное смещение;ошибка измерения со знаком;величина скорости без направления;подписанный баланс;расстояние по одной координате;размер поправки без направления;число на числовой прямой;величина отрицательного показания;отклонение от равновесия;длина направленного шага;подписанное изменение;отклонение датчика;величина координаты без знака;подписанная сила в одной оси;расстояние отметки от начала;подписанная разница;неотрицательная величина числа;величина ошибки без знака;подписанный игровой сдвиг;размер сдвига табло;модуль скалярной величины;абсолютная величина показания',
 'neg':'обратное направление смещения;отражение координаты относительно нуля;противоположная поправка;число для нулевой суммы;смена знака показания;противоположный баланс;обратное направление скорости;отмена направленного вклада;отрицание скалярного числа;противоположная ошибка;обратный направленный шаг;отражение отметки;обратная коррекция;подписанный игровой сдвиг;смена плюса и минуса;аддитивно противоположное число;смена направления координатной величины;равное смещение в другую сторону;противоположное показание датчика;нейтрализация слагаемого;отмена подписанного изменения;смена направления без изменения величины;противоположная величина заряда;обратная арифметическая поправка',
 'square':'площадь квадрата;число ячеек квадратной сетки;число умноженное само на себя;вторая степень величины;квадрат отклонения;два одинаковых множителя;квадрат ошибки измерения;квадрат скалярного показания;площадь квадратного участка;число ячеек квадратной таблицы;вторая степень координаты;площадь квадратной плитки;квадрат длины;произведение двух копий числа;площадь квадратного поля;вторая степень подписанного числа;квадрат результата измерения;двойное вхождение величины в произведение;квадрат параметра игры;квадратный массив клеток;площадь квадрата по стороне;произведение одинаковых показаний;квадрат исходного значения;вторая степень поправки'
}
PARTNER={'+':'-','-':'+','*':'/','/':'*','abs':'neg','neg':'abs','square':'neg'}
SLUG={'+':'add','-':'sub','*':'mul','/':'div','abs':'abs','neg':'neg','square':'square'}


def normalize(text):
    text=re.sub(r'[RР][0-3]','<r>',text.lower(),flags=re.I)
    return re.sub(r'[^а-яёa-z<>]+',' ',text).strip()


def no_side_effects(text):
    pattern=r'\b(?:сохранить|сохрани(?:те)?|записать|запиши(?:те)?|помести(?:ть|те)?|верни(?:те|ть)?|перезаписать)\b[^.!?]{0,110}(?:\bR[0-3]\b|\bобратно\b|\bпамят[ьи]\b)'
    return not re.search(pattern,text,re.I)


def jobs_for(level):
    rng=random.Random(6110710+level);jobs=[]
    if level==1:
        for op,words in TOPICS.items():
            for i,topic in enumerate(words.split(';')):
                for style in range(len(STYLES)):
                    a,b=rng.sample(['R0','R1','R2','R3'],2)
                    first=[op,a,b]if ARITY[op]==2 else[op,a]
                    partner=PARTNER[op];second=[partner,*first[1:]]
                    jobs.append((f'{SLUG[op]}-{i:02}-{style}',first,second,topic,style))
    else:
        # A generic two-operation library; no held-out statement text is read.
        base=[['+',['*','A','B'],'C'],['-','A',['*','B','C']],['*',['+','A','B'],'C'],
              ['/',['+','A','B'],'C'],['abs',['-','A','B']],['square',['+','A','B']],
              ['-',['+','A','B'],'C'],['+',['-','A','B'],'C'],['-','A',['+','B','C']],
              ['*',['-','A','B'],'C'],['/',['-','A','B'],'C'],['/','A',['+','B','C']],
              ['/','A',['*','B','C']],['+',['/','A','B'],'C'],['-',['/','A','B'],'C'],
              ['abs',['+','A','B']],['square',['-','A','B']],['+',['square','A'],'B'],
              ['neg',['+','A','B']],['*',['abs','A'],'B'],['+','A',['abs','B']],
              ['-',['square','A'],'B'],['/',['square','A'],'B'],['neg',['*','A','B']]]
        def subst(e,m):return m[e]if isinstance(e,str)else[e[0],*(subst(x,m)for x in e[1:])]
        for i,expr in enumerate(base):
            for context in range(4):
                for style in range(3):
                    a,b,c=rng.sample(['R0','R1','R2','R3'],3);first=subst(expr,{'A':a,'B':b,'C':c})
                    second=[PARTNER[first[0]],*first[1:]]
                    jobs.append((f'compose-{i:02}-{context}-{style}',first,second,
                       ['простой игровой расчёт','понятная бытовая ситуация','учебный числовой алгоритм','измерения и поправки'][context],style))
    return jobs


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--level',type=int,choices=[1,2],default=1)
    p.add_argument('--workers',type=int,default=4);args=p.parse_args();root=args.root;root.mkdir(parents=True,exist_ok=True)
    if(root/'teacher-manifest.json').exists():print('Reusing completed teacher collection');return
    started=time.monotonic();jobs=jobs_for(args.level);rows=[];errors=[]
    def worker(job):
        key,first,second,topic,style=job
        system=('Создай русские условия для обучения маленькой модели программированию МК-61. '
          'Верни только JSON-массив из ШЕСТИ объектов {"first":"условие A","second":"условие B"}. '
          'Каждый объект — минимальная смысловая пара: общий контекст и близкая формулировка, но другое требуемое действие. '
          'Каждое условие самостоятельно и однозначно описывает свой расчёт. Укажи роли всех нужных регистров. '
          'Каждое условие 6-55 слов. Разные пары должны быть разнообразными по языку и смысловому сюжету. '
          'Не пиши формулу, решение, префиксную запись, байты, примеры числовых входов или ответы. '
          'Регистры R0-R3 только читаются. Результат только в X. Никогда не требуй сохранять ответ в R0-R3. '
          'Не добавляй константы, округление или дополнительные действия. Если сюжет не подходит, опиши абстрактные величины. '
          'abs — модуль, neg — смена знака, square — квадрат. Для деления не требуется целочисленное округление.')
        user=(f'Тема: {topic}. {STYLES[style]}\n'
              f'Алгоритм A в префиксной записи: {prefix(first)}.\nАлгоритм B: {prefix(second)}.\n'
              'Напиши шесть пар. Условия одной пары могут отличаться одним действием или ролью величины, но должны оставаться естественными.')
        values=call(root,'generate',key,[{'role':'system','content':system},{'role':'user','content':user}],tokens=2600,temperature=.9)
        accepted=[]
        for i,item in enumerate(values if isinstance(values,list)else[]):
            if not isinstance(item,dict):continue
            for side,expr in [('first',first),('second',second)]:
                text=item.get(side,'')
                if not isinstance(text,str):continue
                text=re.sub(r'Р([0-3])',r'R\1',text).strip()
                if not 6<=len(text.split())<=65 or not re.search('[а-яё]',text,re.I):continue
                if any(x in text for x in ['<','>','=','```'])or not no_side_effects(text):continue
                mentioned=set(re.findall(r'R[0-9A-F]',text))
                expected=set(re.findall(r'R[0-3]',prefix(expr)))
                if mentioned!=expected:continue
                accepted.append({'id':f'course{args.level}:{key}:{i}:{side}','pair_id':f'{key}:{i}','text':text,
                                 'expression':expr,'root_operator':expr[0],'source_job':key,'level':args.level})
        return accepted
    with ThreadPoolExecutor(max_workers=args.workers)as pool:
        futures={pool.submit(worker,j):j[0]for j in jobs}
        for n,f in enumerate(as_completed(futures),1):
            try:rows+=f.result()
            except Exception as e:errors.append({'job':futures[f],'error':str(e)[:200]})
            if n%8==0 or n==len(jobs):
                status={'phase':'generate','done':n,'total':len(jobs),'accepted':len(rows),'errors':len(errors),'seconds':time.monotonic()-started}
                (root/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    rows.sort(key=lambda r:r['id']);save_jsonl(root/'candidates.jsonl',rows)
    # The original provenance ID contains an operation mnemonic and a pair side.
    # Never expose it to a supposedly blind reader, nor group neighboring pairs.
    shuffled=list(rows);random.Random(6110901+args.level).shuffle(shuffled)
    groups=[shuffled[i:i+16]for i in range(0,len(shuffled),16)]
    def verify(job):
        i,batch=job;identity=f'{i:05}-'+hashlib.sha256(json.dumps(batch,ensure_ascii=False).encode()).hexdigest()[:12]
        system=('Самостоятельно разбери русские арифметические условия. Верни только JSON-массив объектов '
          '{"id":"...","prefix":"..."}. Префикс: операция перед аргументами, без скобок. '
          'Операции + - * / abs neg square. У первых четырёх два аргумента, у остальных один. Листья R0,R1,R2,R3. '
          'Пример формы: - R1 * R0 R2. Не додумывай роли, регистры, константы или действия. '
          'При неоднозначности, лишних условиях или записи результата в исходный регистр верни prefix=null. '
          'Каждое условие независимо; соседние условия не подсказывают ответ.')
        opaque={r['id']:hashlib.sha256(('opaque-course-check:'+r['id']).encode()).hexdigest()[:16]for r in batch}
        values=call(root,'verify-opaque-v2',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps([{'id':opaque[r['id']],'text':r['text']}for r in batch],ensure_ascii=False)}],tokens=1800,temperature=0)
        decoded={v.get('id'):v.get('prefix')for v in values if isinstance(v,dict)}
        good=[];bad=[]
        for row in batch:
            try:valid=canonical(parse_prefix(decoded.get(opaque[row['id']],'')))==canonical(row['expression'])
            except (ValueError,AttributeError,TypeError):valid=False
            (good if valid else bad).append(row)
        return good,bad
    good=[];bad=[]
    with ThreadPoolExecutor(max_workers=args.workers)as pool:
        futures={pool.submit(verify,p):p[0]for p in enumerate(groups)}
        for n,f in enumerate(as_completed(futures),1):
            try:a,b=f.result();good+=a;bad+=b
            except Exception as e:errors.append({'verify':futures[f],'error':str(e)[:200]})
            if n%8==0 or n==len(groups):
                status={'phase':'blind_verify','done':n,'total':len(groups),'verified':len(good),'rejected':len(bad),'errors':len(errors),'seconds':time.monotonic()-started}
                (root/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    save_jsonl(root/'verified-unsplit.jsonl',good);save_jsonl(root/'rejected.jsonl',bad)
    # Whole minimal pairs and register-renamed duplicate wording form one family.
    parent={i:i for i in range(len(good))}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[b]=a
    seen_text={};seen_pair={}
    for i,row in enumerate(good):
        key=normalize(row['text'])
        if key in seen_text:union(i,seen_text[key])
        else:seen_text[key]=i
        if row['pair_id']in seen_pair:union(i,seen_pair[row['pair_id']])
        else:seen_pair[row['pair_id']]=i
    components=collections.defaultdict(list)
    for i in range(len(good)):components[find(i)].append(good[i])
    # Exact overlap with independently authored checks is excluded, never shown
    # to the teacher and never used as gradient examples or selection labels.
    forbidden=set()
    for split in ['validation-manual','fresh']:
        path=root.parent/f'level{args.level}-{split}.jsonl'
        if path.exists():forbidden.update(normalize(json.loads(s)['task'])for s in path.read_text().splitlines())
    partitions={'train':[],'validation':[],'test':[]};excluded=collections.Counter()
    for component in components.values():
        keys=sorted({normalize(r['text'])for r in component})
        if forbidden.intersection(keys):excluded['manual_overlap']+=len(component);continue
        if len(component)>256:excluded['generic_giant_family']+=len(component);continue
        identity=hashlib.sha256(('course-family-v1:'+keys[0]).encode()).hexdigest()
        bucket=int(identity[:8],16)%10;split='validation'if bucket==0 else'test'if bucket==1 else'train'
        unique={normalize(r['text']):r for r in sorted(component,key=lambda r:r['id'])}
        for row in unique.values():partitions[split].append({**row,'split':split,'language_family':identity})
    counts={}
    for split,items in partitions.items():
        items.sort(key=lambda r:r['id']);save_jsonl(root/(split+'.jsonl'),items)
        counts[split]=dict(collections.Counter(r['root_operator']for r in items))
    manifest={'teacher':MODEL,'level':args.level,'jobs':len(jobs),'candidates':len(rows),'verified':len(good),'rejected':len(bad),
      'partitions':{k:len(v)for k,v in partitions.items()},'operator_counts':counts,'excluded':dict(excluded),'errors':errors,
      'split':'Connected minimal-pair and register-neutral wording families, hash split before gradients',
      'fresh_manual_sent_to_teacher':False,'manual_checks_used_only_for_exact_text_decontamination':True,
      'verification':'Opaque random-looking IDs; shuffled classes and minimal-pair sides; checker sees only text and opaque ID',
      'seconds':time.monotonic()-started,'files':{s:hashlib.sha256((root/(s+'.jsonl')).read_bytes()).hexdigest()for s in partitions}}
    if args.level==1 and any(counts['train'].get(op,0)<300 for op in ARITY):
        (root/'insufficient-data.json').write_text(json.dumps(manifest,indent=2)+'\n');raise ValueError('Need at least300 genuine training descriptions per operation')
    (root/'teacher-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (root/'status.json').write_text(json.dumps({'phase':'teacher_complete','partitions':manifest['partitions']})+'\n');print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
