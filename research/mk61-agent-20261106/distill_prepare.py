"""Build verified language-to-expression, program and real failure-repair supervision."""
import argparse
import collections
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import time

from emulator import Emulator
from harness import check_program, feedback, initial_prompt, trace_feedback
from tasks import BUILD, compile_expr, expression_text, family_of, program_text, registers_used, save_jsonl, value_of


def rename(expr,mapping):
    return mapping[expr] if isinstance(expr,str) else [expr[0],*(rename(x,mapping) for x in expr[1:])]


def semantic_prompt(text):
    return ("Разбери условие для МК-61. Выдай только <expr>формула</expr>. "
            "Разрешены R0,R1,R2,R3, +,-,*,/, abs(),neg(),square(). Сохраняй порядок действий.\n"
            "Условие: "+text+"\nФормула: ")


def response(task,diagnosis=None):
    formula=expression_text(task['expression'])
    plan=('исправить; ' if diagnosis else '')+'X='+formula
    return '<plan>'+plan+'</plan><write>'+program_text(task['reference_code'])+'</write><run/>'


def make_task(row,mapping,rng,index):
    expr=rename(row['expression'],mapping)
    text=re.sub(r'[RР]([0-3])',lambda m:mapping['R'+m[1]],row['text'])
    tests=[]
    while len(tests)<7:
        registers={r:rng.choice([1,2,3,4,5,7,9,12]) for r in sorted(registers_used(expr))}
        try:value=value_of(expr,registers)
        except ArithmeticError:continue
        if value.is_finite() and abs(value)<1000000:
            tests.append({'registers':registers,'expected_X':str(value.normalize())})
    return {'id':f'distill:{index}','kind':'synthesis','task':text+' Вход уже в регистрах МК-61. Ответ в X, затем С/П.',
            'expression':expr,'reference_code':compile_expr(expr)+[0x50],
            'public_tests':tests[:2],'hidden_tests':tests[2:],'family':family_of(expr),
            'teacher_source':row['id']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=BUILD/'distill-v1');p.add_argument('--permutations',type=int,default=12)
    args=p.parse_args();root=args.root
    if (root/'data-manifest.json').exists():raise SystemExit('Distillation training data already frozen')
    verified=[json.loads(x) for x in (root/'teacher-verified.jsonl').read_text().splitlines()]
    rng=random.Random(6110603);em=Emulator();rows=[];tasks=[];failures=[];started=time.monotonic()
    permutations=list(itertools.permutations(['R0','R1','R2','R3']))
    for i,row in enumerate(verified):
        choices=rng.sample(permutations,args.permutations)
        for permutation in choices:
            mapping=dict(zip(['R0','R1','R2','R3'],permutation))
            task=make_task(row,mapping,rng,len(tasks))
            checked=check_program(em,task['reference_code'],task['public_tests']+task['hidden_tests'])
            if not checked['pass']:
                failures.append({'id':task['id'],'source':row['id'],'details':checked});continue
            tasks.append(task)
            common={'family':task['family'],'source':'blind_verified_teacher','teacher_source':row['id'],'split':'train'}
            rows.append({**common,'kind':'natural_program','prompt':initial_prompt(task,examples=bool(len(tasks)%2)),
                         'answer':response(task)})
            if len(tasks)%2==0:
                rows.append({**common,'kind':'semantic_formula','prompt':semantic_prompt(task['task']),
                             'answer':'<expr>'+expression_text(task['expression'])+'</expr>'})
            if len(tasks)%3==0:
                code=list(task['reference_code']);position=rng.randrange(len(code)-1)
                candidates=[0x10,0x11,0x12,0x13,0x31,0x0B,0x22] if code[position]<0x60 else [0x60,0x61,0x62,0x63]
                code[position]=rng.choice([x for x in candidates if x!=code[position]])
                broken={**task,'initial_code':code}
                bad=check_program(em,code,task['public_tests'])
                if not bad['pass']:
                    rows.append({**common,'kind':'natural_repair','prompt':initial_prompt(broken,examples=False,observation=feedback(bad)),
                                 'answer':response(task,True)})
                    if len(tasks)%6==0:
                        rows.append({**common,'kind':'natural_trace','prompt':initial_prompt(broken,examples=False),'answer':'<plan>проверить код</plan><trace/>'})
                        rows.append({**common,'kind':'natural_trace_repair','prompt':initial_prompt(broken,examples=False,
                                     observation=trace_feedback(em,code,task['public_tests'][0])),'answer':response(task,True)})
        if (i+1)%100==0 or i+1==len(verified):
            print(json.dumps({'teacher_statements':i+1,'total':len(verified),'tasks_checked':len(tasks),'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    save_jsonl(root/'natural-train-tasks.jsonl',tasks)
    save_jsonl(root/'reference-rejections.jsonl',failures)
    # A fixed diagnostic training-only set is used to collect this model's own errors.
    hard=rng.sample(tasks,min(640,len(tasks)))
    for task in hard:task.pop('initial_code',None)
    save_jsonl(root/'rollout-train-tasks.jsonl',hard)
    replay=[json.loads(x) for x in (BUILD/'training/sft-combined-v2.jsonl').read_text().splitlines()]
    replay=rng.sample(replay,min(10000,len(replay)))
    rows+=replay;rng.shuffle(rows);save_jsonl(root/'train-base.jsonl',rows)
    natural_validation=[json.loads(x) for x in (root/'validation-v2.jsonl').read_text().splitlines()]
    formal=[json.loads(x) for x in (BUILD/'tasks/validation-extended-v2.jsonl').read_text().splitlines()]
    controls=[x for x in formal if x['kind']in ['branch','loop','state']]
    save_jsonl(root/'selection.jsonl',natural_validation+formal[:8]+controls)
    manifest={'teacher_statements':len(verified),'natural_tasks':len(tasks),'rows':len(rows),
              'kinds':dict(collections.Counter(r['kind'] for r in rows)),'reference_rejections':len(failures),
              'actual_emulator_reference_checks':'All seven numerical cases for every accepted augmented task',
              'teacher_generated_test_tasks':False,'original_fresh_test_used_for_training':False,
              'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['train-base.jsonl','natural-train-tasks.jsonl','rollout-train-tasks.jsonl','selection.jsonl']},
              'seconds':time.monotonic()-started}
    (root/'data-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
