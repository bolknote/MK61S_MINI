"""Mine current student errors and executable near misses from TRAIN tasks only."""
import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from emulator import Emulator
from harness import check_program,initial_prompt
from tasks import BUILD,program_text,registers_used,save_jsonl,value_of


def answer(code):return '<write>'+program_text(code)+'</write><run/>'


def main():
    p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=1536);args=p.parse_args()
    root=BUILD/'distill-hard';previous=BUILD/'distill-v1';broad=BUILD/'distill-broad'
    if(root/'data-manifest.json').exists():print('Reusing frozen hard data');return
    em=Emulator();rng=random.Random(6110612)
    excluded={r['id']for r in json.loads((previous/'teacher-side-effect-audit.json').read_text())['excluded_memory_requests']}
    tasks=[json.loads(x)for x in(previous/'natural-train-tasks.jsonl').read_text().splitlines()]
    tasks=[t for t in tasks if t['teacher_source']not in excluded]
    tasks += [json.loads(x)for x in(broad/'train-tasks.jsonl').read_text().splitlines()]
    sample=rng.sample(tasks,min(args.samples,len(tasks)));revised=[]
    for i,original in enumerate(sample):
        t=dict(original);cases=[];expr=t['expression'];tries=0
        sign_words=bool(re.search('отклон|координат|направлен|смещен|противополож|знак',t['task'],re.I))
        while len(cases)<7:
            tries+=1
            if tries>300:raise ValueError('Cannot sample feasible training inputs')
            values=[-17,-8,-3,-1,0,2,4,7,13,19]if sign_words else[1,2,4,6,9,13,17,21]
            regs={r:rng.choice(values)for r in sorted(registers_used(expr))}
            try:value=value_of(expr,regs)
            except ArithmeticError:continue
            if not value.is_finite()or abs(value)>1e6:continue
            case={'registers':regs,'expected_X':str(value.normalize())}
            if check_program(em,t['reference_code'],[case])['pass']:cases.append(case)
        t.update(id=f'hard-train:{i}',public_tests=cases[:2],hidden_tests=cases[2:]);t.pop('initial_code',None);revised.append(t)
    path=root/'rollout-train-tasks.jsonl';save_jsonl(path,revised)
    output=root/'current-train-rollouts.json'
    if not output.exists():
        subprocess.run([sys.executable,str(Path(__file__).with_name('evaluate_batched.py')),'--model',str(previous/'direct-clean/best'),
            '--tasks',str(path),'--output',str(output),'--q4','--no-plan','--batch-size','16'],check=True)
    lookup={t['id']:t for t in revised};rollout=json.loads(output.read_text());pairs=[]
    for detail in rollout['details']:
        task=lookup[detail['id']]
        for entry in detail['history']:
            code=entry.get('code')
            if not code or check_program(em,code,task['public_tests']+task['hidden_tests'])['pass']:continue
            pairs.append({'kind':'actual_student_error','family':task['family'],'prompt':entry['prompt'],
                'chosen':answer(task['reference_code']),'rejected':answer(code),'task':task['id'],'negative_verified':True})
    for i,task in enumerate(revised):
        correct=task['reference_code']
        for _ in range(3):
            wrong=list(correct);position=rng.randrange(len(wrong)-1)
            values=[0x60,0x61,0x62,0x63]if wrong[position]>=0x60 else[0x10,0x11,0x12,0x13,0x31,0x0B,0x22]
            wrong[position]=rng.choice([x for x in values if x!=wrong[position]])
            if check_program(em,wrong,task['public_tests']+task['hidden_tests'])['pass']:continue
            pairs.append({'kind':'verified_near_miss','family':task['family'],'prompt':initial_prompt(task,examples=bool(i%2)),
                'chosen':answer(correct),'rejected':answer(wrong),'task':task['id'],'negative_verified':True})
    pairs=list({(r['prompt'],r['rejected']):r for r in pairs}.values());rng.shuffle(pairs)
    save_jsonl(root/'pairs.jsonl',pairs)
    rows=[json.loads(x)for x in(previous/'train-clean.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['kind']not in['semantic_formula','broad_semantic_formula']]
    for row in rows:row['answer']=re.sub(r'<plan>.*?</plan>','',row['answer'],flags=re.S)
    save_jsonl(root/'train-code.jsonl',rows)
    manifest={'initial_model':'distill-v1/direct-clean/best','training_rollout_tasks':len(revised),
       'training_rollout_passed':rollout['passed'],'pairs':len(pairs),'actual_error_pairs':sum(r['kind']=='actual_student_error'for r in pairs),
       'code_only_sft_rows':len(rows),'all_positive_and_negative_programs_executed':True,
       'fresh_audit_used_for_training':False,
       'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest()for n in['pairs.jsonl','train-code.jsonl','rollout-train-tasks.jsonl']}}
    (root/'data-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
