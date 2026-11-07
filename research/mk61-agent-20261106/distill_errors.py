"""Turn the model's failed TRAIN rollouts into bounded, executable repair examples."""
import hashlib
import argparse
import json
from pathlib import Path
import random
import re
import subprocess
import sys

from distill_prepare import response
from harness import initial_prompt
from tasks import BUILD, save_jsonl


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--clean-output',action='store_true');args=parser.parse_args()
    root=BUILD/'distill-v1'
    teacher=[json.loads(x)for x in(root/'teacher-verified.jsonl').read_text().splitlines()]
    # The expression-only blind check cannot certify memory side effects.
    # Reject explicit requests to store the result in a named input register.
    store=re.compile(r'\b(?:сохранить|сохрани(?:те)?|записать|запиши(?:те)?|помести(?:ть|те)?|верни(?:те|ть)?|перезаписать)\b[^.!?]{0,120}(?:\b[RР][0-3]\b|\bобратно\b|\bпамят[ьи]\b)',re.I)
    destination=re.compile(r'\b(?:результат|ответ|итог)\w*[^.!?]{0,70}(?:оказаться|храниться|содержаться|лежать|попасть|записан|сохран[её]н)[^.!?]{0,40}\b[RР][0-3]\b',re.I)
    excluded=[r for r in teacher if store.search(r['text'])or destination.search(r['text'])]
    allowed={r['id']for r in teacher}-{r['id']for r in excluded}
    (root/'teacher-side-effect-audit.json').write_text(json.dumps({'statements_before':len(teacher),'statements_retained':len(allowed),
        'excluded_memory_requests':excluded,'filter':'Conservative regex for unlabelled memory writes; arithmetic references specify X only'},ensure_ascii=False,indent=2)+'\n')
    tasks={r['id']:r for r in [json.loads(x) for x in (root/'rollout-train-tasks.jsonl').read_text().splitlines()]}
    rollout=json.loads((root/'own-train-rollouts.json').read_text())
    rows=[]
    for detail in rollout['details']:
        task=tasks[detail['id']]
        if task['teacher_source']not in allowed:continue
        for entry in detail['history']:
            if entry.get('code') and entry.get('public_result',{}).get('pass')is False:
                rows.append({'source':'own_training_error','split':'train','family':task['family'],'kind':'own_error_repair',
                    'prompt':initial_prompt({**task,'initial_code':entry['code']},examples=False,observation=entry['feedback']),
                    'answer':response(task,True)})
    current_rollout_rows=0
    if args.clean_output and(BUILD/'distill-broad/train-tasks.jsonl').exists():
        broad_tasks=[json.loads(s)for s in(BUILD/'distill-broad/train-tasks.jsonl').read_text().splitlines()]
        chosen=max(['structured','direct'],key=lambda a:tuple(json.loads((root/a/'training.json').read_text())['selection_key']))
        sample=random.Random(6110608).sample(broad_tasks,min(512,len(broad_tasks)))
        sample_path=root/'current-broad-train-tasks.jsonl';save_jsonl(sample_path,sample)
        result_path=root/'current-broad-own-rollouts.json'
        if not result_path.exists():
            command=[sys.executable,str(Path(__file__).with_name('evaluate_batched.py')),'--model',str(root/chosen/'best'),
                     '--tasks',str(sample_path),'--output',str(result_path),'--q4','--batch-size','16']
            if chosen=='direct':command.append('--no-plan')
            subprocess.run(command,check=True)
        lookup={t['id']:t for t in sample}
        current=json.loads(result_path.read_text())
        for detail in current['details']:
            task=lookup[detail['id']]
            for entry in detail['history']:
                if entry.get('code')and entry.get('public_result',{}).get('pass')is False:
                    rows.append({'source':'current_teacher_model_training_error','split':'train','family':task['family'],
                        'kind':'current_own_error_repair','prompt':initial_prompt({**task,'initial_code':entry['code']},examples=False,observation=entry['feedback']),
                        'answer':response(task,True)})
                    current_rollout_rows+=1
    # Repeated identical failures are a single learning example, then mixed with base SFT.
    rows=list({r['prompt']:r for r in rows}.values());corrections=rows
    save_jsonl(root/'own-error-repairs.jsonl',corrections)
    base=[json.loads(x) for x in (root/'train-base.jsonl').read_text().splitlines()]
    original_base=len(base)
    base=[r for r in base if not r.get('teacher_source')or r['teacher_source']in allowed]
    broad_rows=0
    if args.clean_output:
        broad=BUILD/'distill-broad/train.jsonl'
        if broad.exists():
            more=[json.loads(s)for s in broad.read_text().splitlines()]
            broad_rows=len(more);base+=more
    # About 15% of examples address actual errors, with no test information involved.
    rng=random.Random(6110604)
    extra=[dict(rng.choice(corrections)) for _ in range(len(base)//6)]if corrections else []
    combined=base+extra;rng.shuffle(combined)
    output_name='train-clean.jsonl'if args.clean_output else'train.jsonl'
    save_jsonl(root/output_name,combined)
    manifest_name='own-error-clean-manifest.json'if args.clean_output else'own-error-manifest.json'
    (root/manifest_name).write_text(json.dumps({'unique_real_error_prompts':len(corrections),'mixed_error_rows':len(extra),
        'training_rows':len(combined),'training_only_rollout_tasks':len(tasks),'teacher_statements_retained':len(allowed),
        'unlabelled_memory_write_rows_excluded':original_base-(len(base)-broad_rows),'broad_rows':broad_rows,
        'current_teacher_model_failed_turns':current_rollout_rows,
        'sha256':hashlib.sha256((root/output_name).read_bytes()).hexdigest()},indent=2)+'\n')
    print((root/manifest_name).read_text())


if __name__=='__main__':main()
