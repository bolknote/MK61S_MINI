"""Numerically verify a frozen teacher split and prepare a balanced curriculum."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import shutil

from course_common import ARITY,make_task
from emulator import Emulator
from evaluate import read_tasks
from tasks import BUILD,save_jsonl


def prepare(root,level):
    output=root/f'course-level{level}';source=root/f'teacher-level{level}'
    output.mkdir(exist_ok=True)
    if(output/'manifest.json').exists():return
    teacher=json.loads((source/'teacher-manifest.json').read_text())
    frozen=json.loads((root/'frozen.json').read_text())
    for name,record in frozen['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Frozen evaluation input changed: '+name)
    snapshot=output/'source';snapshot.mkdir(exist_ok=True)
    source_hashes={}
    for file in Path(__file__).parent.glob('*.py'):
        if file.name.startswith(('course_','capacity_'))or file.name in ['lowbit.py','quantization.py','train.py','harness.py','evaluate_batched.py','tasks.py','emulator.py']:
            shutil.copyfile(file,snapshot/file.name);source_hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    em=Emulator();rng=random.Random(6110800+level);counts={};hashes={}
    for split in ['train','validation','test']:
        path=source/(split+'.jsonl')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==teacher['files'][split]
        rows=read_tasks(path);tasks=[]
        if split!='train':
            groups=collections.defaultdict(list)
            for row in rows:groups[row['root_operator']].append(row)
            # Fixed disjoint teacher language families, never manual/fresh text.
            rows=[]
            for op in ARITY:
                pool=groups[op];rng.shuffle(pool);rows+=pool[:16 if split=='validation'else 14]
        for i,row in enumerate(rows):
            task=make_task(row['text'],row['expression'],rng,row['id'],level=level,split=split,emulator=em)
            task.update({k:row[k]for k in ['pair_id','language_family','root_operator','source_job']})
            tasks.append(task)
            if i%500==0:print(json.dumps({'preparing':split,'verified':i,'total':len(rows)}),flush=True)
        target=output/(split+'.jsonl');save_jsonl(target,tasks)
        counts[split]=dict(collections.Counter(t['expression'][0]for t in tasks))
        hashes[split]=hashlib.sha256(target.read_bytes()).hexdigest()
    formal=read_tasks(BUILD/'tasks/validation-extended-v2.jsonl')
    # Preserve the same small formal control panel in both model sizes.
    formal=formal[:12]+[t for t in formal if t['kind']in{'branch','loop','state'}][:8]
    save_jsonl(output/'formal-validation.jsonl',formal)
    replay=[]
    for row in read_tasks(BUILD/'training/control-v2-sft.jsonl'):
        prompt=re.sub(r'<plan>.*?</plan>','',row['prompt'],flags=re.S)
        answer=re.sub(r'<plan>.*?</plan>','',row['answer'],flags=re.S)
        replay.append({'prompt':prompt,'answer':answer})
    rng.shuffle(replay);save_jsonl(output/'formal-replay.jsonl',replay[:6000])
    manifest={'level':level,'counts':counts,'sha256':hashes,'teacher_manifest':teacher,
              'all_numerical_references_executed':True,'public_cases':2,'hidden_cases':7,
              'register_permutations_are_augmentation_not_unique_wordings':True,
              'manual_validation_or_fresh_used_in_gradients':False,'fresh_opened_for_scoring':False,
              'formal_replay_rows':min(len(replay),6000),'formal_development_rows':len(formal),
              'learned_calc_prefix_before_model_written_bytecode':True,'source_sha256':source_hashes}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--level',type=int,required=True)
    a=p.parse_args();prepare(a.root,a.level)
