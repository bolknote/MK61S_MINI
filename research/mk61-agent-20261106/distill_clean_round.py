"""Complete both live teacher runs, clean annotation side effects, then evaluate once."""
import argparse
import json
import os
import subprocess
import sys
import time

from distill_round import REPO,BASE,ROOT,REL,ROUND,SCRIPT,status,assess


def worker(arm):
    os.environ['MK61_AGENT_GPU']='0'if arm=='structured'else'1'
    from run_experiment import run
    run('distill-v1/'+arm+'-clean.log',SCRIPT+'train.py','--phase','sft','--initial',ROUND+arm+'/best',
        '--data',ROUND+'train-clean.jsonl','--tasks',ROUND+'selection.jsonl','--output',ROUND+arm+'-clean',
        '--steps','4000','--batch','32','--micro-batch','16','--context','512','--lr','0.00005','--qat-start','1',
        '--eval-every','250','--development-all','--natural-selection','--eval-batch-size','16','--prompt-limit','352',
        *(['--no-plan']if arm=='direct'else []))


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['structured','direct']);args=p.parse_args()
    if args.worker:worker(args.worker);return
    status('teacher_sft_then_clean_continuation',initial_steps=6000,clean_steps=4000)
    deadline=time.monotonic()+14400
    while not all((ROOT/arm/'training.json').exists()for arm in ['structured','direct']):
        if time.monotonic()>deadline:raise TimeoutError('Initial teacher training not complete')
        time.sleep(10)
    from run_experiment import run
    status('waiting_for_broader_teacher_data')
    deadline=time.monotonic()+14400
    while not(BASE/'distill-broad/data-manifest.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Broad teacher data preparation not complete')
        time.sleep(10)
    status('annotation_quality_cleanup')
    if not(ROOT/'own-error-clean-manifest.json').exists():
        run('distill-v1/clean-data.log',SCRIPT+'distill_errors.py','--clean-output')
    status('clean_teacher_sft',steps_each=4000,qat_start=1)
    processes=[]
    for arm in ['structured','direct']:
        log=(ROOT/(arm+'-clean-controller.log')).open('w')
        proc=subprocess.Popen([sys.executable,'-u',__file__,'--worker',arm],cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        processes.append((arm,proc,log))
    for arm,proc,log in processes:
        code=proc.wait();log.close()
        if code:raise RuntimeError('Clean training failed: '+arm)
    status('validation_selection')
    for arm in ['structured','direct']:
        assess(ROUND+arm+'-clean/best',arm+'-clean-q4-validation',ROUND+'selection.jsonl',no_plan=arm=='direct')
    def rank(arm):
        d=json.loads((ROOT/'results'/(arm+'-clean-q4-validation.json')).read_text());n=d['by_kind']['natural_language']
        ft=d['total']-n['total'];fp=d['passed']-n['passed']
        return (fp/max(1,ft)>=.95,n['passed']/n['total'],fp/max(1,ft),arm=='direct')
    selected=max(['structured','direct'],key=rank)
    (ROOT/'preselected.json').write_text(json.dumps({'arm':selected+'-clean','keys':{a:rank(a)for a in ['structured','direct']},
        'fresh_audit_used_for_selection':False},indent=2)+'\n')
    status('final_q4_and_fp32_evaluation',preselected=selected+'-clean')
    for arm in ['structured','direct']:
        name=arm+'-clean'
        for split,path in [('fresh-russian-v2',ROUND+'fresh-russian-v2.jsonl'),('formal',REL+'tasks/test-extended-v2.jsonl'),
                           ('opened-diagnostic',REL+'language-data/audit.jsonl')]:
            for q4 in [True,False]:
                assess(ROUND+name+'/best',name+('-q4-'if q4 else'-fp32-')+split,path,q4=q4,no_plan=arm=='direct')
        run('distill-v1/'+name+'-semantic-q4.log',SCRIPT+'semantic_eval.py','--model',ROUND+name+'/best',
            '--tasks',ROUND+'fresh-russian-v2.jsonl','--output',ROUND+'results/'+name+'-semantic-q4.json','--q4')
    status('teacher_round_complete',preselected=selected+'-clean')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if '--worker'not in sys.argv:status('failed',error=f'{type(error).__name__}: {error}')
        raise
