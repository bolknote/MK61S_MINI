"""Current-student states and whole candidate execution comparisons, train only."""
import copy
import json
import random
from ac_common import ROOT,read,write
from ac_eval import tool_panel,generate
from ac_teacher import make_session,expert,grade,forced_path,preference
from ha_protocol import assemble,encode
from full_isa_vm import FullVM
from tasks import save_jsonl


def mine(model,tokenizer,arm,block):
    tasks=read(ROOT/'train.jsonl');lookup={t['id']:t for t in tasks}
    level=json.loads((ROOT/f'level-{block}.json').read_text())['level']
    items=[i for i in read(ROOT/'train-seeds.jsonl')if lookup[i['task_id']].get('level',1)<=level]
    rng=random.Random(811901+block);rng.shuffle(items);items=items[:160]
    panel,lessons=tool_panel(model,tokenizer,tasks,items,mine=True)
    pairs=[];vm=FullVM()
    # Sample full WRITE candidates at the same real states, even if the policy
    # currently chooses DONE. These are explicitly off-policy training candidates.
    candidates=items[:80]
    for at in range(0,len(candidates),16):
        batch=candidates[at:at+16];sessions=[make_session(lookup[x['task_id']],x,vm)for x in batch]
        replies=generate(model,tokenizer,[s.request()for s in sessions],forced_action='write',sample=True)
        for item,s,g in zip(batch,sessions,replies):
            # Existing verified wrong/correct branches are always included.
            pairs.append(preference(s.task,item,vm))
            if g['codec_error']or not g['body']:continue
            try:
                candidate=assemble(g['body'],s.pool,'asm')
            except ValueError:continue
            current=assemble(s.body,s.pool,'asm')
            new={**item,'initial_code':current,'candidate_code':candidate,'intentionally_correct':False}
            check=make_session(s.task,new,vm)
            if grade(check):continue
            p=preference(s.task,new,vm);p['kind']='current_student_wrong_full_WRITE_then_DONE';pairs.append(p)
    save_jsonl(ROOT/f'onpolicy-{block}-{arm}.jsonl',lessons)
    save_jsonl(ROOT/f'preferences-{block}-{arm}.jsonl',pairs)
    write(ROOT/f'mining-{block}-{arm}.json',panel)
    print(json.dumps({'arm':arm,'block':block,'states':len(lessons),'whole_episode_preferences':len(pairs),
                      'actual_false_DONE':panel['false_DONE']}),flush=True)
