"""Systematic distinct-input compositions, plus blinded teacher paraphrases."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor,as_completed
from functools import lru_cache
import hashlib
import json
import random
import re
import time

from compose_common import ROOT,read,make_task,expression_words,stack_depth
from course_common import ARITY,canonical,parse_prefix
from course_teacher import normalize,no_side_effects
from emulator import Emulator,build
from tasks import family_of,split_of,expression_text,registers_used,save_jsonl
from teacher_data import call,MODEL


@lru_cache(None)
def shapes(n):
    if n==0:return ['v']
    result=[]
    for op,arity in ARITY.items():
        if arity==1:result += [[op,x]for x in shapes(n-1)]
        else:
            for left in range(n):result += [[op,a,b]for a in shapes(left)for b in shapes(n-1-left)]
    return result


def distinct(expr,names):
    iterator=iter(names)
    def replace(x):return next(iterator)if isinstance(x,str)else[x[0],*(replace(y)for y in x[1:])]
    return replace(expr)


def wording_key(text):
    mapping={}
    def replace(match):
        name=match.group().upper();mapping.setdefault(name,'input'+str(len(mapping)));return mapping[name]
    return re.sub(r'[^а-яёa-z0-9]+',' ',re.sub(r'R[0-3]',replace,text,flags=re.I).lower()).strip()


def ordered_words(expr):
    steps=[];names=['первого','второго','третьего']
    def visit(x):
        if isinstance(x,str):return x
        args=[visit(y)for y in x[1:]];op=x[0]
        if op=='+':text=f'сложи {args[0]} и {args[1]}'
        elif op=='-':text=f'вычти {args[1]} из {args[0]}'
        elif op=='*':text=f'перемножь {args[0]} и {args[1]}'
        elif op=='/':text=f'раздели {args[0]} на {args[1]}'
        elif op=='abs':text=f'возьми абсолютную величину {args[0]}'
        elif op=='neg':text=f'смени знак {args[0]}'
        else:text=f'возведи {args[0]} в квадрат'
        steps.append(text);return 'результат '+names[len(steps)-1]+' действия'
    visit(expr)
    return '. '.join(('Сначала 'if i==0 else'Затем ')+x for i,x in enumerate(steps))+'. Итог последнего действия оставь в X.'


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',type=int,choices=[2,3],required=True);a=p.parse_args()
    out=ROOT/f'balanced-phase{a.phase}';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():return
    rng=random.Random(6113400+a.phase);em=Emulator(build(out/'libbalanced-reference.so'))
    heldout={normalize(t['task'])for name in ['fresh1','fresh2','fresh3','development1','development2','development3']for t in read(ROOT/(name+'.jsonl'))}
    heldout.update(normalize(t['task'])for split in ['validation','test']for t in read(ROOT/f'course/{split}.jsonl'))
    existing={wording_key(t['task'])for t in read(ROOT/'course/train.jsonl')}
    bank={};procedural=[];rejected=collections.Counter()
    for level in [2,3]:
        for skeleton in shapes(level):
            family=family_of(skeleton)
            if family in bank:continue
            names=rng.sample(['R0','R1','R2','R3'],4);expr=distinct(skeleton,names)
            if len(registers_used(expr))<2 or split_of(expr)!='train' or stack_depth(expr)>4:continue
            try:base=make_task('',expr,rng,'balanced:'+hashlib.sha256(family.encode()).hexdigest()[:16],split='train',emulator=em)
            except ValueError:rejected['invalid_reference']+=1;continue
            bank[family]=base
            texts=['Вычисли '+expression_words(expr,style)+'. Исходные числа уже в регистрах, результат нужен в X.'for style in range(3)]
            texts += [ordered_words(expr)]
            for style,text in enumerate(texts):
                key=wording_key(text)
                if normalize(text)in heldout or key in existing:continue
                procedural.append({**base,'id':base['id']+':'+str(style),'task':text,
                  'source':'teacher_refresh','origin':'systematic_distinct_input_procedural',
                  'pair_id':base['id'],'language_family':base['id']});existing.add(key)
    groups=collections.defaultdict(list)
    for row in bank.values():groups[(row['level'],len(registers_used(row['expression'])))].append(row)
    selected=[]
    for key,rows in groups.items():rng.shuffle(rows);selected+=rows[:64]
    def generate(row):
        system=('Придумай ровно два различных русских условия для точно заданного выражения. '
          'Ответ только JSON-массив из двух строк. Первое — краткая инструкция словами с порядком действий; '
          'второе — практический сюжет с вопросом и понятными ролями величин. По12-55 слов. '
          'Каждый R0,R1,R2,R3 в выражении обозначает отдельное исходное число. '
          'В точности сохрани все действия, порядок вычитания и деления. Не добавляй новые действия, числа, '
          'регистры, округление, сохранение в исходные регистры. Не пиши формулу, пример значений, код или ответ. Итог нужен в X.')
        identity=hashlib.sha256(row['id'].encode()).hexdigest()[:20]
        values=call(out,'single-ast',identity,[{'role':'system','content':system},{'role':'user','content':
          'Выражение: '+expression_text(row['expression'])+'\nТочный порядок: '+ordered_words(row['expression'])}],tokens=1300,temperature=.6)
        result=[]
        for i,text in enumerate(values if isinstance(values,list)else[]):
            if not isinstance(text,str):continue
            text=re.sub(r'Р([0-3])',r'R\1',text).strip()
            if not 8<=len(text.split())<=70 or any(c in text for c in '<>=`')or not no_side_effects(text):continue
            if set(re.findall(r'R[0-9A-F]',text))!=registers_used(row['expression']):continue
            result.append({**row,'id':row['id']+':teacher'+str(i),'task':text,'source':'teacher_refresh',
              'origin':'systematic_distinct_input_teacher','pair_id':row['id'],'language_family':row['id']})
        return result
    candidates=[];errors=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        for n,f in enumerate(as_completed([executor.submit(generate,row)for row in selected]),1):
            try:candidates+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if n%10==0:(out/'status.json').write_text(json.dumps({'phase':'generation','done':n,'total':len(selected),'procedural':len(procedural),'candidates':len(candidates)})+'\n')
    rng.shuffle(candidates);batches=[candidates[i:i+12]for i in range(0,len(candidates),12)]
    def verify(index,rows):
        opaque={hashlib.sha256(('balanced-reader:'+r['id']).encode()).hexdigest()[:20]:r for r in rows}
        system=('Восстанови арифметическое выражение по каждому русскому условию независимо. JSON-массив '
          '{"id":"...","prefix":"..."}. Префикс без скобок; + - * / имеют два аргумента; abs neg square один. '
          'Листья R0,R1,R2,R3. При неоднозначности, пропущенных ролях, новых числах или лишних действиях верни null. '
          'Не делай выводов по соседним условиям.')
        identity=str(index)+'-'+hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()[:12]
        values=call(out,'blind',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':key,'text':row['task']}for key,row in opaque.items()],ensure_ascii=False)}],tokens=2300,temperature=0)
        decoded={x.get('id'):x.get('prefix')for x in values if isinstance(x,dict)};result=[]
        for key,row in opaque.items():
            try:correct=canonical(parse_prefix(decoded.get(key,'')))==canonical(row['expression'])
            except (ValueError,TypeError,AttributeError):correct=False
            if correct:result.append(row)
        return result
    verified=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        for f in as_completed([executor.submit(verify,i,rows)for i,rows in enumerate(batches)]):
            try:verified+=f.result()
            except Exception as e:errors.append(str(e)[:200])
    teacher=[]
    for row in verified:
        key=wording_key(row['task'])
        if normalize(row['task'])in heldout or key in existing:continue
        teacher.append(row);existing.add(key)
    # Wait for the other independent training-only augmentation before merging.
    started=time.monotonic()
    while not(ROOT/f'augmentation-phase{a.phase}/manifest.json').exists():
        if time.monotonic()-started>1800:raise TimeoutError('Other own augmentation did not complete')
        time.sleep(10)
    status=json.loads((ROOT/'status.json').read_text());too_late=status.get('course_phase',0)>=a.phase or status['phase']in ['closed_fresh_evaluation','complete']
    path=ROOT/f'phase{a.phase}-extra-train.jsonl';old=read(path)if path.exists()else[]
    combined=old+procedural+teacher
    if not too_late:
        temp=path.with_suffix('.balanced-tmp');save_jsonl(temp,combined);temp.replace(path)
    report={'source':'systematic_shapes_with_distinct_inputs','procedural':len(procedural),'teacher_generated':len(candidates),
      'blind_verified':len(verified),'teacher_added':len(teacher),'previous_augmentation':len(old),'total':len(combined),
      'families':len(bank),'by_level_and_distinct_inputs':{str(k):len(v)for k,v in groups.items()},
      'rejected':dict(rejected),'errors':errors,'saved_for_next_phase':not too_late,
      'heldout_or_manual_gradient_targets':False,'training_dedup_preserves_register_equality_pattern':True}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','rows':len(combined),'saved_for_next_phase':not too_late})+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
