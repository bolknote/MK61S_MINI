"""Prepare additional TRAINING-only language variety before a later shared phase."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import random
import re

from compose_common import ROOT,read,make_task
from compose_balanced import wording_key
from course_common import canonical,parse_prefix
from course_teacher import normalize,no_side_effects
from emulator import Emulator,build
from tasks import expression_text,registers_used,save_jsonl
from teacher_data import call,MODEL


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',type=int,choices=[2,3],required=True);a=p.parse_args()
    out=ROOT/f'augmentation-phase{a.phase}';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():return
    pool=read(ROOT/'course/train.jsonl');rng=random.Random(6113300+a.phase);selected=[]
    for level in [1,2,3]:
        groups=collections.defaultdict(list)
        for row in pool:
            if row['level']==level and row['source']!='procedural':groups[row['expression'][0]].append(row)
        for rows in groups.values():rng.shuffle(rows);selected+=rows[:24]
    rng.shuffle(selected)
    def generate(index,row):
        system=('Составь два новых самостоятельных русских условия для одного точно заданного выражения. '
          'Ответ JSON-массив из двух строк. Первое — очень короткая разговорная просьба с обозначениями величин '
          'в регистрах; второе — понятный сюжет с вопросом. По8-40 слов. '
          'Оба текста должны задавать ровно указанное выражение, с точным порядком вычитания и деления. '
          'Объясни все нужные исходные R0,R1,R2,R3, не добавляй другие регистры. '
          'Не пиши формулу, HEX-код, числа-примеры, решение или новые операции, константы, округление. '
          'Исходные регистры только читаются, итог нужен в X. Измени лексику и синтаксис исходного учебного условия.')
        identity=hashlib.sha256((str(a.phase)+':'+row['id']).encode()).hexdigest()[:20]
        values=call(out,'single-expression',identity,[{'role':'system','content':system},{'role':'user','content':
          'Выражение: '+expression_text(row['expression'])+'\nИсходное учебное условие: '+row['task']}],tokens=1100,temperature=.6)
        result=[]
        for n,text in enumerate(values if isinstance(values,list)else[]):
            if not isinstance(text,str):continue
            text=re.sub(r'Р([0-3])',r'R\1',text).strip()
            if not 6<=len(text.split())<=60 or any(c in text for c in '<>=`')or not no_side_effects(text):continue
            if set(re.findall(r'R[0-9A-F]',text))!=registers_used(row['expression']):continue
            result.append({'id':f'augmentation{a.phase}:{identity}:{n}','text':text,'expression':row['expression'],
              'level':row['level'],'parent_training_id':row['id'],'language_family':row['language_family']})
        return result
    candidates=[];errors=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        futures=[executor.submit(generate,i,row)for i,row in enumerate(selected)]
        for n,f in enumerate(as_completed(futures),1):
            try:candidates+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if n%20==0:
                (out/'status.json').write_text(json.dumps({'phase':'generation','done':n,'total':len(selected),'candidates':len(candidates)})+'\n')
    candidates.sort(key=lambda r:r['id']);rng.shuffle(candidates);batches=[candidates[i:i+12]for i in range(0,len(candidates),12)]
    def verify(index,rows):
        opaque={hashlib.sha256(('augmentation-blind:'+r['id']).encode()).hexdigest()[:20]:r for r in rows}
        system=('Независимо разбери арифметические условия. Ответ JSON-массив {"id":"...","prefix":"..."}. '
          'Префикс — операция перед аргументами без скобок. + - * / имеют два аргумента; abs neg square один. '
          'Листья R0,R1,R2,R3. neg значит противоположное число. При неоднозначности, неполных ролях, '
          'лишних числах или действиях, изменении исходных регистров ответ prefix=null. Не угадывай по соседним строкам.')
        identity=str(index)+'-'+hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()[:12]
        values=call(out,'blind',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':key,'text':r['text']}for key,r in opaque.items()],ensure_ascii=False)}],tokens=2000,temperature=0)
        decoded={v.get('id'):v.get('prefix')for v in values if isinstance(v,dict)};good=[]
        for key,row in opaque.items():
            try:valid=canonical(parse_prefix(decoded.get(key,'')))==canonical(row['expression'])
            except (ValueError,TypeError,AttributeError):valid=False
            if valid:good.append(row)
        return good
    verified=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        for f in as_completed([executor.submit(verify,i,rows)for i,rows in enumerate(batches)]):
            try:verified+=f.result()
            except Exception as e:errors.append(str(e)[:200])
    forbidden={normalize(r['task'])for p in ROOT.glob('*.jsonl')for r in read(p)if'task'in r}
    existing_training={wording_key(r['task'])for r in pool}
    em=Emulator(build(out/'libcompose-augmentation.so'));tasks=[];seen=set();rejected=collections.Counter()
    for row in verified:
        key=wording_key(row['text'])
        if normalize(row['text'])in forbidden or key in existing_training or key in seen:rejected['exact_existing_or_heldout_text']+=1;continue
        try:task=make_task(row['text'],row['expression'],rng,row['id'],split='train',emulator=em)
        except ValueError:rejected['invalid_numerical_reference']+=1;continue
        task.update(source='teacher_refresh',pair_id=row['id'],language_family=row['language_family'],parent_training_id=row['parent_training_id'])
        tasks.append(task);seen.add(key)
    status=json.loads((ROOT/'status.json').read_text());too_late=status.get('course_phase',0)>=a.phase or status['phase']in ['closed_fresh_evaluation','complete']
    if tasks and not too_late:
        path=ROOT/f'phase{a.phase}-extra-train.jsonl';temp=path.with_suffix('.tmp');save_jsonl(temp,tasks);temp.replace(path)
    manifest={'teacher':MODEL,'source_training_conditions':len(selected),'generated':len(candidates),'blind_verified':len(verified),
      'reference_verified':len(tasks),'rejected':dict(rejected),'errors':errors,'saved_for_next_phase':bool(tasks)and not too_late,
      'optional_minimum300_novel_examples_reached':len(tasks)>=300,
      'all_sources_from_training':True,'manual_or_fresh_sent_to_teacher':False,'target_phase':a.phase}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','rows':len(tasks),'saved_for_next_phase':bool(tasks)and not too_late})+'\n')
    print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
