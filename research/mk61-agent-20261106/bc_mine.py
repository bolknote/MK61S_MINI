"""Mine current SPEC under the unchanged self-check protocol, on train only."""
import argparse
import collections
import json
import random
import torch
from bc_common import ROOT,read,rows,write,save_rows,sha,compact_head,output_ids
from bc_model import load
from bc_self import desired
from ba_lessons import wrong_program,make_row
from ay_eval import primary
from az_runtime import Session
from ar_spec import verify
from full_isa_vm import FullVM
from aq_eval import generate

def main(shard):
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/f'mined-{shard}.json').exists():return
    values=sorted({g['id']:g for g in rows(ROOT/'train-clean.jsonl')}.values(),key=lambda g:g['id'])
    rng=random.Random(26110864);rng.shuffle(values);values=values[:128][shard::2]
    assert all(g['split']=='train'for g in values)
    model,tokenizer=load();compact_head(model,output_ids(tokenizer));vm=FullVM()
    proposals={r['id']:r for r in primary(model,tokenizer,values,'spec',vm)};jobs=[];out=[];counts=collections.Counter()
    for g in values:
        bad=wrong_program(g,vm,'argument')[0]
        for body in [g['reference_body'],bad]:jobs.append((g,Session(g,body,vm,'spec',proposals[g['id']]['declared_spec'],True)))
    for at in range(0,len(jobs),24):
        chunk=jobs[at:at+24]
        for turn in range(6):
            active=[(g,s)for g,s in chunk if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            generations=generate(model,tokenizer,[s.request()for g,s in active])
            for(g,s),v in zip(active,generations):
                correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
                action,body,reason=desired(s,correct)
                origin=('conflict_unsure'if reason=='visible_check_conflict'else'self_repair'if action=='write'else'self_done'if action=='done'else action)
                if not s.diagnosis:
                    row=make_row(g,s,action,origin,correct,body,True);row.update(curriculum='parent_self_mining',teacher_reason=reason,
                        parent_generation=v,parent_wrong_DONE=v.get('action')=='done'and not correct)
                    out.append(row);counts[origin]+=1;counts['parent_wrong_DONE']+=row['parent_wrong_DONE']
                if v.get('codec_error'):s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError):s.exhausted=True
        print(json.dumps({'shard':shard,'jobs':min(at+24,len(jobs)),'lessons':len(out),'counts':dict(counts)}),flush=True)
    file=ROOT/f'mined-{shard}.jsonl';save_rows(file,out)
    write(ROOT/f'mined-{shard}.json',{'rows':len(out),'counts':dict(counts),'file_sha256':sha(file),'only_train_goals':True,'SGD_updates':0})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--shard',type=int,choices=[0,1],required=True);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main(a.shard)
