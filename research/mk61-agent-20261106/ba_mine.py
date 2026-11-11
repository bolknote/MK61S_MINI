"""Mine the frozen parent only on training goals, with live bounded sessions."""
import argparse
import collections
import json
import random
import torch
from ba_common import ROOT,rows,write,save_rows,sha,compact_head,output_ids
from ba_model import load
from ba_pools import goal_layout
from az_runtime import Session,snapshot
from az_lessons import mutant
from ay_data import op_count
from ar_spec import verify
from full_isa_vm import FullVM
from aq_eval import generate


def main(shard):
    assert not(ROOT/'frozen.json').exists()
    marker=ROOT/f'mined-{shard}.json'
    if marker.exists():return
    groups={g['id']:g for g in rows(ROOT/'train-clean.jsonl')};values=sorted(groups.values(),key=lambda g:g['id'])
    rng=random.Random(26110844);rng.shuffle(values);values=values[:128][shard::2]
    assert all(g['split']=='train'for g in values)
    model,tokenizer=load();compact_head(model,output_ids(tokenizer));vm=FullVM();jobs=[];lessons=[];counts=collections.Counter()
    for g in values:
        for mode in ['default','full']:
            item=goal_layout(g,mode,g['id']+':mine:'+mode);_,bad=mutant(item,vm,'argument')
            jobs += [(item,Session(item,body,vm,'spec'))for body in [item['reference_body'],bad]]
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24]
        for turn in range(4):
            active=[(g,s)for g,s in chunk if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for g,s in active];generations=generate(model,tokenizer,prompts)
            for(g,s),generation in zip(active,generations):
                correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
                if not s.diagnosis:
                    if not s.eligibility()[0]:
                        missing=[i for i in [0,1]if i not in s.runs];action='run'if missing else'write';body=[missing[0]]if missing else[]
                    else:action='done'if correct else'write';body=[]
                    origin='repair'if action=='write'else action
                    wrong=not(action==generation.get('action')and(action!='run'or generation.get('body')==body))
                    row={'id':f'ba:mined:{shard}:{len(lessons):06}','group_id':g['id'],'state':snapshot(s),'action':action,'body':body,
                         'origin':origin,'correctness':int(correct),'target_spec':g['spec'],'reference_body':g['reference_body'],'spec_body':g['spec_body'],
                         'simple':op_count(g['spec']['X'])<=2,'family':g['family'],'curriculum':'parent_mining','priority':wrong,
                         'parent_generation':generation,'parent_wrong_DONE':generation.get('action')=='done'and not correct}
                    lessons.append(row);counts[action]+=1;counts['parent_wrong_DONE']+=row['parent_wrong_DONE']
                if generation.get('codec_error'):s.exhausted=True;continue
                try:s.apply_action(generation['action'],generation['body'])
                except (ValueError,ArithmeticError,RuntimeError):s.exhausted=True
        print(json.dumps({'shard':shard,'jobs':min(at+24,len(jobs)),'lessons':len(lessons),'counts':dict(counts)}),flush=True)
    path=ROOT/f'mined-{shard}.jsonl';save_rows(path,lessons)
    write(marker,{'rows':len(lessons),'counts':dict(counts),'file_sha256':sha(path),'only_train_goals':True,'SGD_updates':0})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--shard',type=int,choices=[0,1],required=True);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main(a.shard)
