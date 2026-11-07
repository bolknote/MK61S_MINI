"""Merge only training sources, check numerical references and freeze context cases."""
import collections
import hashlib
import json
from pathlib import Path
import random
import re

from course_common import make_task
from course_teacher import normalize,no_side_effects
from emulator import Emulator
from tasks import BUILD,save_jsonl,split_of,registers_used


def read(path):return [json.loads(x)for x in path.read_text().splitlines()]


def main():
    root=BUILD/'native-mixed-v1';out=root/'course';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():print('Course already prepared');return
    frozen=json.loads((root/'frozen.json').read_text())
    for name,v in frozen['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==v['sha256']
    old=BUILD/'capacity-v1';em=Emulator();rng=random.Random(6111801)
    manual_keys={normalize(r['task'])for name in ['development-manual.jsonl','fresh-level1.jsonl','fresh-level2.jsonl']for r in read(root/name)}
    datasets={}
    for split in ['train','validation','test']:
        original=read(old/f'course-level1/{split}.jsonl')
        compact=read(root/f'teacher/{split}.jsonl')
        records=[{**r,'text':r['task']}for r in original]+compact
        datasets[split]=records
    # Any register-neutral wording shared across splits is excluded from train.
    heldout_keys={normalize(r['text'])for s in ['validation','test']for r in datasets[s]}
    counts={};excluded=collections.Counter()
    for split,records in datasets.items():
        unique={}
        for row in records:
            key=normalize(row['text'])
            if split=='train'and(key in manual_keys or key in heldout_keys):excluded['train_overlap']+=1;continue
            unique.setdefault(key,row)
        tasks=[]
        for i,row in enumerate(unique.values()):
            task=make_task(row['text'],row['expression'],rng,row['id'],level=1,split=split,emulator=em)
            task.update(pair_id=row['pair_id'],language_family=row.get('language_family','old:'+row['id']))
            tasks.append(task)
            if i%500==0:print(json.dumps({'reference_check':split,'done':i,'total':len(unique)}),flush=True)
        save_jsonl(out/(split+'.jsonl'),tasks);counts[split]=len(tasks)
    # Fixed balanced development panel, with both old and compact teacher style.
    validation=read(out/'validation.jsonl');groups=collections.defaultdict(list)
    for row in validation:groups[row['expression'][0]].append(row)
    selected=[]
    for op,pool in groups.items():rng.shuffle(pool);selected+=pool[:24]
    save_jsonl(out/'teacher-development.jsonl',selected)
    compound=[];compound_keys=set()
    def opcount(expr):return 0 if isinstance(expr,str)else 1+sum(opcount(x)for x in expr[1:])
    destination=re.compile(r'\b(?:результат|ответ|итог)\w*[^.!?]{0,70}(?:оказаться|храниться|содержаться|лежать|попасть|записан|сохран[её]н)[^.!?]{0,40}\b[RР][0-3]\b',re.I)
    for collection in ['distill-v1','distill-broad']:
        for row in read(BUILD/collection/'teacher-verified.jsonl'):
            expr=row['expression'];text=row['text'];k=normalize(text)
            if opcount(expr)!=2 or len(registers_used(expr))<2 or split_of(expr)!='train':continue
            if not no_side_effects(text)or destination.search(text)or k in manual_keys or k in compound_keys:continue
            try:task=make_task(text,expr,rng,'native-compose:'+collection+':'+row['id'],level=2,split='train',emulator=em)
            except ValueError:excluded['compound_invalid_reference_or_domain']+=1;continue
            if len({x['expected_X']for x in task['public_tests']+task['hidden_tests']})<3:continue
            task.update(pair_id=task['id'],language_family=row['family']);compound.append(task);compound_keys.add(k)
    save_jsonl(out/'compound-train.jsonl',compound)
    (out/'formal-development.jsonl').write_bytes((old/'course-level1/formal-validation.jsonl').read_bytes())
    (out/'formal-replay.jsonl').write_bytes((old/'recovery-replay.jsonl').read_bytes())
    manifest={'counts':counts,'teacher_development':len(selected),'excluded':dict(excluded),
      'all_references_checked_in_microcode_emulator':True,'manual_or_fresh_added_as_gradient_targets':False,
      'training_sha256':hashlib.sha256((out/'train.jsonl').read_bytes()).hexdigest(),
      'source_teacher':json.loads((root/'teacher/manifest.json').read_text()),'compound_train':len(compound),
      'compound_progression':'Both arms include25% composed conditions after step4000 only if either arm clears the same basic validation gate'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
