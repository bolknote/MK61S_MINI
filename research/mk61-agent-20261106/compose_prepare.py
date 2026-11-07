"""Verify references and build a shared, decontaminated two/three-op course."""
import collections
import json
import random

from compose_common import ROOT,read,sha,make_task,opcount,stack_depth,expression_words
from course_common import canonical
from course_teacher import normalize
from emulator import Emulator
from tasks import BUILD,random_expr,split_of,registers_used,save_jsonl


def main():
    out=ROOT/'course';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():print('Composition course already verified');return
    assert(ROOT/'teacher/manifest.json').exists()
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,entry in frozen['files'].items():assert sha(ROOT/name)==entry['sha256']
    em=Emulator();rng=random.Random(6112901)
    forbidden={normalize(x['task'])for p in ROOT.glob('*.jsonl')for x in read(p)}
    teacher={s:read(ROOT/f'teacher/{s}.jsonl')for s in ['train','validation','test']}
    forbidden.update(normalize(r['text'])for s in ['validation','test']for r in teacher[s])
    candidates=[]
    for row in read(BUILD/'native-mixed-v1/course/train.jsonl'):
        candidates.append({**row,'text':row['task'],'source':'elementary_legacy'})
    for row in read(BUILD/'native-mixed-v1/course/compound-train.jsonl'):
        candidates.append({**row,'text':row['task'],'source':'compound_legacy'})
    candidates += [{**row,'source':'teacher_new'}for row in teacher['train']]
    seen_expr=set();generated=0;attempts=0
    # These are explicitly labelled procedural descriptions, not human stories.
    while generated<1600:
        attempts+=1
        if attempts>500000:raise ValueError('Procedural expression coverage stalled')
        level=2 if generated%4==0 else 3;expr=random_expr(rng,3)
        if isinstance(expr,str)or opcount(expr)!=level or split_of(expr)!='train' or stack_depth(expr)>4 or len(registers_used(expr))<2:continue
        key=canonical(expr)
        if key in seen_expr:continue
        try:probe=make_task('',expr,rng,'probe',split='train',emulator=em)
        except ValueError:continue
        seen_expr.add(key)
        for style in range(3):
            text='Вычисли '+expression_words(expr,style)+'. Результат оставь в X, исходные регистры не меняй.'
            candidates.append({**probe,'id':f'procedural:{generated}:{style}','text':text,
              'pair_id':f'procedural:{generated}','language_family':f'procedural:{generated}',
              'source':'procedural','level':level})
        generated+=1
    rejected=collections.Counter();unique={};train=[]
    for i,row in enumerate(candidates):
        key=normalize(row['text']);level=opcount(row['expression'])
        if key in forbidden:rejected['observed_or_heldout_wording']+=1;continue
        if key in unique:continue
        if level>1 and split_of(row['expression'])!='train':raise ValueError('Structural heldout entered multi-op training')
        try:task=make_task(row['text'],row['expression'],rng,row['id'],split='train',emulator=em)
        except ValueError:rejected['invalid_or_degenerate_reference']+=1;continue
        task.update(source=row['source'],pair_id=row.get('pair_id',row['id']),language_family=row.get('language_family',row['id']))
        unique[key]=True;train.append(task)
        if i%1000==0:print(json.dumps({'reference_checked':i,'total':len(candidates),'retained':len(train)}),flush=True)
    save_jsonl(out/'train.jsonl',train)
    panels={}
    for split in ['validation','test']:
        values=[]
        for row in teacher[split]:
            try:task=make_task(row['text'],row['expression'],rng,row['id'],split=split,emulator=em)
            except ValueError:rejected[split+'_invalid_reference']+=1;continue
            values.append({**task,'pair_id':row['pair_id'],'language_family':row['language_family']})
        save_jsonl(out/(split+'.jsonl'),values);panels[split]=len(values)
    (out/'formal-replay.jsonl').write_bytes((BUILD/'native-mixed-v1/course/formal-replay.jsonl').read_bytes())
    (out/'formal-development.jsonl').write_bytes((BUILD/'tasks/validation-extended-v2.jsonl').read_bytes())
    report={'train':len(train),'counts_by_level':dict(collections.Counter(t['level']for t in train)),
      'counts_by_source':dict(collections.Counter(t['source']for t in train)),
      'validation_test_counts':panels,'rejected':dict(rejected),'training_sha256':sha(out/'train.jsonl'),
      'all_references_checked_in_microcode':True,'fresh_or_manual_targets_added':False,
      'structural_multioperation_training_split':'Only split_of(AST)==train',
      'procedural_descriptions_are_separately_labelled':True}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
