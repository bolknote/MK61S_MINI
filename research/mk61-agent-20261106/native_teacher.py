"""Short Russian conditions with value-like register annotations; opaque checks."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import time

from tasks import BUILD,save_jsonl
from course_common import canonical,parse_prefix,prefix
from course_teacher import normalize,no_side_effects
from teacher_data import call,MODEL


def rows(path):return [json.loads(x)for x in path.read_text().splitlines()]


def main():
    root=BUILD/'native-mixed-v1';out=root/'teacher';out.mkdir(parents=True,exist_ok=True)
    if(out/'manifest.json').exists():print('Teacher collection complete');return
    jobs=[];rng=random.Random(6111702)
    for split,limit in [('train',200),('validation',20),('test',20)]:
        source=rows(BUILD/f'capacity-v1/teacher-level1/{split}.jsonl');groups=collections.defaultdict(list)
        for row in source:groups[row['expression'][0]].append(row)
        selected=[]
        for op,pool in groups.items():rng.shuffle(pool);selected += [{**r,'native_split':split}for r in pool[:limit]]
        rng.shuffle(selected)
        jobs += [selected[i:i+8]for i in range(0,len(selected),8)]
    started=time.monotonic();generated=[];errors=[]
    def generate(index,batch):
        mapping={hashlib.sha256(('native-rewrite:'+r['id']).encode()).hexdigest()[:16]:r for r in batch}
        system=('Перепиши условия арифметических задач для МК-61 кратко по-русски. Верни JSON-массив '
          'объектов {"id":"полученный id","texts":["вариант1","вариант2"]}. '
          'Смысл и роли регистров сохраняются точно. Два самостоятельных варианта по5-30 слов. '
          'Первый: короткое естественное условие с вопросом. Второй: сжатая запись величин и просьба получить результат. '
          'Используй обозначение числа после названия величины, например название параметра и R0; '
          'избегай стандартного начала В регистре хранится. R0-R3 обозначают исходные числа. '
          'Не добавляй другие числа, формулы, константы, операции, округление, исходные примеры или ответ. '
          'Входные регистры только читаются, результат в X. Каждый вариант однозначен сам по себе.')
        values=call(out,'rewrite',str(index),[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':key,'condition':r['text'],'algorithm':prefix(r['expression'])}for key,r in mapping.items()],ensure_ascii=False)}],tokens=2300,temperature=.8)
        result=[]
        for value in values if isinstance(values,list)else[]:
            if not isinstance(value,dict)or value.get('id')not in mapping:continue
            original=mapping[value['id']]
            for n,text in enumerate(value.get('texts',[])):
                if not isinstance(text,str):continue
                text=re.sub(r'Р([0-3])',r'R\1',text).strip()
                if not 5<=len(text.split())<=40 or any(c in text for c in '<>=`')or not no_side_effects(text):continue
                if set(re.findall(r'R[0-9A-F]',text))!=set(re.findall(r'R[0-3]',prefix(original['expression']))):continue
                result.append({'id':original['id']+f':compact{n}','text':text,'expression':original['expression'],
                  'pair_id':original['pair_id'],'language_family':original['language_family'],'split':original['native_split']})
        return result
    with ThreadPoolExecutor(max_workers=4)as pool:
        futures=[pool.submit(generate,i,batch)for i,batch in enumerate(jobs)]
        for n,f in enumerate(as_completed(futures),1):
            try:generated+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if n%10==0 or n==len(jobs):
                status={'phase':'rewriting','done':n,'total':len(jobs),'rows':len(generated),'errors':len(errors)}
                (out/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    generated.sort(key=lambda r:r['id']);rng.shuffle(generated);save_jsonl(out/'candidates.jsonl',generated)
    batches=[generated[i:i+16]for i in range(0,len(generated),16)];verified=[]
    def verify(index,batch):
        opaque={hashlib.sha256(('native-blind:'+r['id']).encode()).hexdigest()[:16]:r for r in batch}
        system=('Независимо разбери арифметические условия. Верни JSON-массив {"id":"...","prefix":"..."}. '
          'Префиксная запись без скобок, операция перед аргументами. + - * / имеют2 аргумента, abs neg square один. '
          'Листья R0,R1,R2,R3. При неоднозначности, дополнительных константах, действиях или сохранении в исходные регистры prefix=null. '
          'Не угадывай по соседним условиям.')
        values=call(out,'verify-opaque',str(index),[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':k,'text':r['text']}for k,r in opaque.items()],ensure_ascii=False)}],tokens=1800,temperature=0)
        decoded={v.get('id'):v.get('prefix')for v in values if isinstance(v,dict)}
        result=[]
        for key,row in opaque.items():
            try:correct=canonical(parse_prefix(decoded.get(key,'')))==canonical(row['expression'])
            except (ValueError,TypeError,AttributeError):correct=False
            if correct:result.append(row)
        return result
    with ThreadPoolExecutor(max_workers=4)as pool:
        futures=[pool.submit(verify,i,batch)for i,batch in enumerate(batches)]
        for n,f in enumerate(as_completed(futures),1):
            try:verified+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if n%10==0 or n==len(batches):
                status={'phase':'blind_verification','done':n,'total':len(batches),'retained':len(verified),'errors':len(errors)}
                (out/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    forbidden={normalize(r['task'])for name in ['fresh-level1.jsonl','fresh-level2.jsonl','development-manual.jsonl']for r in rows(root/name)}
    partitions={};seen={};excluded=0
    for row in verified:
        key=normalize(row['text'])
        if key in forbidden:excluded+=1;continue
        if key in seen:
            if seen[key]['split']!=row['split']:seen.pop(key);forbidden.add(key)
            continue
        seen[key]=row
    for split in ['train','validation','test']:
        part=sorted([r for k,r in seen.items()if r['split']==split and k not in forbidden],key=lambda r:r['id'])
        save_jsonl(out/(split+'.jsonl'),part);partitions[split]=len(part)
    if partitions['train']<1800:raise ValueError('Insufficient verified compact Russian conditions')
    result={'teacher':MODEL,'partitions':partitions,'generated':len(generated),'verified':len(verified),'errors':errors,
      'exact_manual_overlap_excluded':excluded,'checker_inputs':'Only text and opaque IDs, mixed classes',
      'splits':'Inherited whole language families from old train/validation/test; new rewrites retain source split',
      'fresh_sent_to_teacher':False,'seconds':time.monotonic()-started}
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(out/'status.json').write_text(json.dumps({'phase':'complete','partitions':partitions})+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
