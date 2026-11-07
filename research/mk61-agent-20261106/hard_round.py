"""Compare contrastive and text-first learning without reusing the opened audit."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2];BASE=REPO/'.build/mk61-agent-20261106';ROOT=BASE/'distill-hard'
REL='.build/mk61-agent-20261106/';HARD=REL+'distill-hard/';SCRIPT='research/mk61-agent-20261106/'


def status(phase,**extra):
    value={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)


def assess(model,label,tasks,*,q4=True,hidden=False):
    from run_experiment import run
    if(ROOT/'results'/(label+'.json')).exists():return
    run('distill-hard/'+label+'.log',SCRIPT+'evaluate_batched.py','--model',model,'--tasks',tasks,
        '--output',HARD+'results/'+label+'.json','--no-plan','--batch-size','16',
        *(['--q4']if q4 else[]),*(['--hide-public-inputs']if hidden else[]))


def worker(arm):
    os.environ['MK61_AGENT_GPU']='0'if arm=='dpo'else'1'
    from run_experiment import run
    initial=REL+'distill-v1/direct-clean/best'
    if arm=='dpo':
        run('distill-hard/dpo.log',SCRIPT+'hard_train.py','--initial',initial,'--data',HARD+'train-code.jsonl',
            '--pairs',HARD+'pairs.jsonl','--tasks',HARD+'selection.jsonl','--output',HARD+'dpo','--steps','2000')
    else:
        run('distill-hard/text-only.log',SCRIPT+'train.py','--phase','sft','--initial',initial,'--data',HARD+'train-code.jsonl',
            '--tasks',HARD+'selection.jsonl','--output',HARD+'text-only','--steps','4000','--batch','32','--micro-batch','16',
            '--context','512','--lr','0.00005','--qat-start','1','--eval-every','250','--development-all','--natural-selection',
            '--eval-batch-size','16','--prompt-limit','352','--no-plan','--hide-public-inputs')


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['dpo','text-only']);args=p.parse_args()
    if args.worker:worker(args.worker);return
    ROOT.mkdir(exist_ok=True)
    from run_experiment import run
    initial=REL+'distill-v1/direct-clean/best'
    status('new_frozen_baseline')
    assess(initial,'baseline-q4-fresh',HARD+'fresh-russian.jsonl')
    assess(initial,'baseline-q4-validation',HARD+'selection.jsonl')
    assess(initial,'baseline-hidden-q4-validation',HARD+'selection.jsonl',hidden=True)
    status('collect_current_errors_and_near_misses')
    if not(ROOT/'data-manifest.json').exists():run('distill-hard/prepare.log',SCRIPT+'hard_prepare.py')
    status('contrastive_and_text_first_training',arms=['dpo','text-only'])
    jobs=[]
    for arm in ['dpo','text-only']:
        log=(ROOT/(arm+'-controller.log')).open('w')
        proc=subprocess.Popen([sys.executable,'-u',__file__,'--worker',arm],cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        jobs.append((arm,proc,log))
    for arm,proc,log in jobs:
        code=proc.wait();log.close()
        if code:raise RuntimeError('Hard worker failed: '+arm)
    status('validation_selection')
    models={'baseline':(initial,False),'dpo':(HARD+'dpo/best',False),'text-only':(HARD+'text-only/best',True)}
    for arm,(model,hidden)in models.items():assess(model,arm+'-q4-validation',HARD+'selection.jsonl',hidden=hidden)
    def rank(arm):
        d=json.loads((ROOT/'results'/(arm+'-q4-validation.json')).read_text());n=d['by_kind']['natural_language'];ft=d['total']-n['total'];fp=d['passed']-n['passed']
        return(fp/max(1,ft)>=.95,n['passed']/n['total'],fp/max(1,ft),-['baseline','dpo','text-only'].index(arm))
    selected=max(models,key=rank)
    (ROOT/'preselected.json').write_text(json.dumps({'arm':selected,'keys':{a:rank(a)for a in models},'fresh_audit_used_for_selection':False},indent=2)+'\n')
    status('final_execution_checks',preselected=selected)
    for arm,(model,hidden)in models.items():
        for split,tasks in [('fresh',HARD+'fresh-russian.jsonl'),('formal',REL+'tasks/test-extended-v2.jsonl'),
                            ('opened-audit',REL+'distill-v1/fresh-russian-v2.jsonl')]:
            for q4 in [True,False]:
                assess(model,arm+('-q4-'if q4 else'-fp32-')+split,tasks,q4=q4,hidden=hidden)
    status('hard_round_complete',preselected=selected)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if '--worker'not in sys.argv:status('failed',error=f'{type(error).__name__}: {error}')
        raise
