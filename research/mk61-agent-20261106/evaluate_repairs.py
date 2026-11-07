"""Explicit hybrid metric: model attempts followed by bounded automatic repair."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from emulator import Emulator
from harness import check_program
import repair_search
from repair_search import search


def repair_result(source,task,em,*,budget=512):
    row={'id':source['id'],'kind':source['kind'],'model_pass':source['pass'],'hybrid_pass':source['pass']}
    # The controller cannot observe a hidden failure after public PASS.
    if not source['pass']and not source.get('public_pass',False):
        result=search(em,source.get('code'),task['public_tests'],budget=budget)
        row['repair']=result
        if result['found']:
            checked=check_program(em,result['code'],task['hidden_tests'])
            row.update(hybrid_pass=checked['pass'],hidden_result=checked)
    return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--tasks',type=Path,required=True);p.add_argument('--model-results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--budget',type=int,default=512);args=p.parse_args()
    tasks={t['id']:t for t in[json.loads(s)for s in args.tasks.read_text().splitlines()]}
    model=json.loads(args.model_results.read_text());em=Emulator();rows=[];started=time.monotonic()
    for i,source in enumerate(model['details']):
        task=tasks[source['id']];row=repair_result(source,task,em,budget=args.budget)
        rows.append(row)
        if(i+1)%16==0:print(json.dumps({'evaluated':i+1,'model_passed':sum(r['model_pass']for r in rows),'hybrid_passed':sum(r['hybrid_pass']for r in rows),'seconds':time.monotonic()-started}),flush=True)
    report={'total':len(rows),'model_passed':sum(r['model_pass']for r in rows),'hybrid_passed':sum(r['hybrid_pass']for r in rows),
            'emulator_candidate_trials':sum(r.get('repair',{}).get('trials',0)for r in rows),'candidate_budget_per_failed_task':args.budget,
            'seconds':time.monotonic()-started,'model_results_sha256':hashlib.sha256(args.model_results.read_bytes()).hexdigest(),
            'tasks_sha256':hashlib.sha256(args.tasks.read_bytes()).hexdigest(),'search_source_sha256':hashlib.sha256(Path(repair_search.__file__).read_bytes()).hexdigest(),
            'method':'Existing model attempts, then automatic bounded search on PUBLIC numerical examples only; hidden tests grade the first public-fitting candidate',
            'requires_user_or_harness_supplied_expected_examples':True,'is_neural_model_accuracy':False,'details':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
