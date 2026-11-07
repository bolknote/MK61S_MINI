"""Verify additional ordinary-language tasks, without opening the fresh audit."""
import hashlib
import itertools
import json
import random
import re
import time

from distill_prepare import make_task,response,semantic_prompt
from emulator import Emulator
from harness import check_program,feedback,initial_prompt
from tasks import BUILD,expression_text,save_jsonl


def main():
    root=BUILD/'distill-broad';deadline=time.monotonic()+14400
    while not(root/'teacher-manifest.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Broad teacher not complete')
        time.sleep(5)
    if(root/'data-manifest.json').exists():print('Reusing completed broad data');return
    rng=random.Random(6110607);em=Emulator();rows=[];tasks=[];excluded=[];rejected=0;started=time.monotonic()
    teacher=[json.loads(s)for s in(root/'teacher-verified.jsonl').read_text().splitlines()]
    store=re.compile(r'\b(?:сохранить|сохрани(?:те)?|записать|запиши(?:те)?|помести(?:ть|те)?|верни(?:те|ть)?|перезаписать)\b[^.!?]{0,120}(?:\b[RР][0-3]\b|\bобратно\b|\bпамят[ьи]\b)',re.I)
    permutations=list(itertools.permutations(['R0','R1','R2','R3']))
    for i,source in enumerate(teacher):
        if store.search(source['text']):excluded.append(source['id']);continue
        for permutation in rng.sample(permutations,4):
            mapping=dict(zip(['R0','R1','R2','R3'],permutation));task=make_task(source,mapping,rng,len(tasks))
            task['id']='broad:'+task['id']
            if not check_program(em,task['reference_code'],task['public_tests']+task['hidden_tests'])['pass']:
                rejected+=1;continue
            tasks.append(task)
            common={'source':'broad_blind_verified_teacher','family':task['family'],'teacher_source':'broad:'+source['id'],'split':'train'}
            rows.append({**common,'kind':'broad_natural_program','prompt':initial_prompt(task,examples=bool(len(tasks)%2)),'answer':response(task)})
            if len(tasks)%2==0:
                rows.append({**common,'kind':'broad_semantic_formula','prompt':semantic_prompt(task['task']),'answer':'<expr>'+expression_text(task['expression'])+'</expr>'})
            if len(tasks)%3==0:
                code=list(task['reference_code']);pos=rng.randrange(len(code)-1)
                options=[0x10,0x11,0x12,0x13,0x31,0x0B,0x22]if code[pos]<0x60 else[0x60,0x61,0x62,0x63]
                code[pos]=rng.choice([x for x in options if x!=code[pos]])
                checked=check_program(em,code,task['public_tests'])
                if not checked['pass']:
                    rows.append({**common,'kind':'broad_natural_repair','prompt':initial_prompt({**task,'initial_code':code},examples=False,observation=feedback(checked)),'answer':response(task,True)})
        if(i+1)%100==0:print(json.dumps({'statements':i+1,'total':len(teacher),'tasks':len(tasks),'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    save_jsonl(root/'train.jsonl',rows);save_jsonl(root/'train-tasks.jsonl',tasks)
    manifest={'teacher_statements':len(teacher),'excluded_unlabelled_memory_requests':excluded,'tasks':len(tasks),'rows':len(rows),
              'reference_rejections':rejected,'all_seven_cases_executed':True,'fresh_audit_opened':False,
              'sha256':hashlib.sha256((root/'train.jsonl').read_bytes()).hexdigest(),'seconds':time.monotonic()-started}
    (root/'data-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
