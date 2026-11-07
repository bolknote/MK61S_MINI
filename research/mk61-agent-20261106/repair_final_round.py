"""Apply a preregistered repair policy to the validation-selected model only."""
import json
import subprocess
import sys
import time
from pathlib import Path

from hard_round import ROOT,REPO,HARD,REL,SCRIPT


def main():
    deadline=time.monotonic()+14400
    while not(ROOT/'preselected.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Hard selection not complete')
        time.sleep(5)
    selected=json.loads((ROOT/'preselected.json').read_text())['arm']
    policy=json.loads((ROOT/'repair-policy.json').read_text())
    from run_experiment import run
    for split,tasks in [('validation',HARD+'selection.jsonl'),('fresh',HARD+'fresh-russian.jsonl'),
                         ('formal',REL+'tasks/test-extended-v2.jsonl')]:
        path=ROOT/'results'/f'{selected}-q4-{split}.json'
        while not path.exists():
            if time.monotonic()>deadline:raise TimeoutError('Model results not complete')
            time.sleep(3)
        # Results are written once. Wait for a complete JSON document.
        while True:
            try:json.loads(path.read_text());break
            except json.JSONDecodeError:time.sleep(1)
        run('distill-hard/repair-'+split+'.log',SCRIPT+'evaluate_repairs.py','--tasks',tasks,
            '--model-results',HARD+f'results/{selected}-q4-{split}.json','--output',HARD+f'repair-{split}.json',
            '--budget',str(policy['candidate_budget']))
    (ROOT/'repair-complete.json').write_text(json.dumps({'selected_base':selected,'policy':policy,'hidden_tests_used_for_search':False},indent=2)+'\n')


if __name__=='__main__':main()
