"""Teacher round controller, isolated from previous rounds and other agents' jobs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
BASE=REPO/'.build/mk61-agent-20261106'
ROOT=BASE/'distill-v1'
SCRIPT='research/mk61-agent-20261106/'
REL='.build/mk61-agent-20261106/'
ROUND=REL+'distill-v1/'


def status(phase,**extra):
    value={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value),flush=True)


def assess(model,label,tasks,*,q4=True,no_plan=False):
    from run_experiment import run
    output=ROOT/'results'/(label+'.json')
    if output.exists():return
    run('distill-v1/'+label+'.log',SCRIPT+'evaluate_batched.py','--model',model,'--tasks',tasks,
        '--output',ROUND+'results/'+label+'.json','--batch-size','16',*(['--q4']if q4 else []),*(['--no-plan']if no_plan else []))


def worker(arm):
    os.environ['MK61_AGENT_GPU']='0'if arm=='structured'else'1'
    from run_experiment import run
    run('distill-v1/'+arm+'.log',SCRIPT+'train.py','--phase','sft','--initial',REL+'language-plan/best',
        '--data',ROUND+'train.jsonl','--tasks',ROUND+'selection.jsonl','--output',ROUND+arm,
        '--steps','6000','--batch','32','--micro-batch','16','--context','512','--lr','0.00008','--qat-start','1001',
        '--eval-every','500','--development-all','--natural-selection','--eval-batch-size','16','--prompt-limit','352',
        *(['--no-plan']if arm=='direct'else []))


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['structured','direct']);p.add_argument('--wait-existing-preparation',action='store_true');args=p.parse_args()
    if args.worker:worker(args.worker);return
    ROOT.mkdir(parents=True,exist_ok=True)
    # All baseline outputs are kept outside the trainer and selector inputs.
    status('fresh_baseline')
    for name,model,no_plan in [('original',REL+'flourish-original',False),('previous-plan',REL+'language-plan/best',False),
                               ('previous-direct',REL+'language-no-plan/best',True)]:
        assess(model,'baseline-'+name+'-q4-fresh-russian-v2',ROUND+'fresh-russian-v2.jsonl',no_plan=no_plan)
    status('waiting_for_teacher')
    deadline=time.monotonic()+14400
    while not(ROOT/'teacher-manifest.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Teacher generation not complete after four hours')
        time.sleep(10)
    manifest=json.loads((ROOT/'teacher-manifest.json').read_text())
    if manifest['verified']<1200:raise ValueError('Too little verified teacher data')
    from run_experiment import run
    status('prepare_verified_language_data',teacher_statements=manifest['verified'])
    if args.wait_existing_preparation:
        deadline=time.monotonic()+1800
        while not(ROOT/'data-manifest.json').exists():
            if time.monotonic()>deadline:raise TimeoutError('Existing data preparation did not finish')
            time.sleep(5)
    if not(ROOT/'data-manifest.json').exists():
        run('distill-v1/prepare.log',SCRIPT+'distill_prepare.py')
    # Refresh the pre-gradient numerical-domain revision of validation, while
    # preserving teacher data and reference programs from the completed worker.
    import hashlib
    natural=[json.loads(s)for s in(ROOT/'validation-v2.jsonl').read_text().splitlines()]
    formal=[json.loads(s)for s in(BASE/'tasks/validation-extended-v2.jsonl').read_text().splitlines()]
    controls=[x for x in formal if x['kind']in['branch','loop','state']]
    selection_path=ROOT/'selection.jsonl'
    selection_path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in natural+formal[:8]+controls))
    data_manifest=json.loads((ROOT/'data-manifest.json').read_text())
    data_manifest['files']['selection.jsonl']=hashlib.sha256(selection_path.read_bytes()).hexdigest()
    data_manifest['validation_probes']='v2, corrected before gradients'
    (ROOT/'data-manifest.json').write_text(json.dumps(data_manifest,ensure_ascii=False,indent=2)+'\n')
    status('collect_own_training_errors')
    if not(ROOT/'own-train-rollouts.json').exists():
        run('distill-v1/own-train-rollouts.log',SCRIPT+'evaluate_batched.py','--model',REL+'language-plan/best',
            '--tasks',ROUND+'rollout-train-tasks.jsonl','--output',ROUND+'own-train-rollouts.json','--q4','--batch-size','16')
    if not(ROOT/'own-error-manifest.json').exists():
        run('distill-v1/mix-errors.log',SCRIPT+'distill_errors.py')
    status('teacher_sft',arms=['structured','direct'],steps_each=6000,qat_start=1001)
    jobs=[]
    for arm in ['structured','direct']:
        log=(ROOT/(arm+'-controller.log')).open('w')
        proc=subprocess.Popen([sys.executable,'-u',__file__,'--worker',arm],cwd=REPO,stdin=subprocess.DEVNULL,
                              stdout=log,stderr=subprocess.STDOUT);jobs.append((arm,proc,log))
    for arm,proc,log in jobs:
        code=proc.wait();log.close()
        if code:raise RuntimeError('Training worker failed: '+arm)
    # Preselect using validation only, before opening the post-training fresh audit.
    status('validation_selection')
    for arm in ['structured','direct']:
        assess(ROUND+arm+'/best',arm+'-q4-validation',ROUND+'selection.jsonl',no_plan=arm=='direct')
    def selection(arm):
        d=json.loads((ROOT/'results'/(arm+'-q4-validation.json')).read_text())
        n=d['by_kind']['natural_language'];f_total=d['total']-n['total'];f_pass=d['passed']-n['passed']
        return (f_pass/max(1,f_total)>=.95,n['passed']/n['total'],f_pass/max(1,f_total),arm=='direct')
    selected=max(['structured','direct'],key=selection)
    (ROOT/'preselected.json').write_text(json.dumps({'arm':selected,'keys':{a:selection(a)for a in ['structured','direct']},
        'fresh_audit_used_for_selection':False},indent=2)+'\n')
    status('final_q4_and_fp32_evaluation',preselected=selected)
    for arm in ['structured','direct']:
        for split,path in [('fresh-russian-v2',ROUND+'fresh-russian-v2.jsonl'),('formal',REL+'tasks/test-extended-v2.jsonl'),
                           ('opened-diagnostic',REL+'language-data/audit.jsonl')]:
            for q4 in [True,False]:
                assess(ROUND+arm+'/best',arm+('-q4-'if q4 else'-fp32-')+split,path,q4=q4,no_plan=arm=='direct')
    status('teacher_round_complete',preselected=selected)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if '--worker'not in sys.argv:status('failed',error=f'{type(error).__name__}: {error}')
        raise
