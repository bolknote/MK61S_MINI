"""Paired composition courses, adaptive extra phases and one closed final audit."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
import random
from pathlib import Path
import subprocess
import sys
import time

from compose_common import ROOT,ARMS,read
from run_experiment import run,REPO,SCRIPT
from tasks import save_jsonl


def status(phase,**extra):
    record={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)


def container_path(path):
    value=Path(path)
    return str(value.relative_to(REPO))if value.is_absolute()else str(value)


def worker(arm,gpu,action,phase,initial=None):
    env={**os.environ,'MK61_AGENT_GPU':str(gpu)}
    args=[sys.executable,'-u',SCRIPT+'compose_round.py','worker',arm,action,str(phase)]
    if initial:args.append(container_path(initial))
    with(ROOT/f'{arm}-{action}{phase}-controller.log').open('a')as log:
        result=subprocess.run(args,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'Failed own {arm} {action} phase{phase}')


def parallel(action,phase,initials=None):
    with ThreadPoolExecutor(max_workers=2)as pool:
        fs=[pool.submit(worker,arm,i,action,phase,(initials or{}).get(arm))for i,arm in enumerate(ARMS)]
        for f in fs:f.result()


def main():
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action,phase=sys.argv[2:5];initial=sys.argv[5]if len(sys.argv)>5 else None
        if action=='train':run(f'composition-v1/{arm}-phase{phase}.log',SCRIPT+'compose_train.py','--arm',arm,'--phase',phase,'--initial',initial,'--steps','8000',timeout=21600)
        elif action=='feedback':run(f'composition-v1/{arm}-feedback{phase}.log',SCRIPT+'compose_feedback.py','--arm',arm,'--phase',phase,timeout=3600)
        else:run(f'composition-v1/{arm}-{action}.log',SCRIPT+'compose_eval.py','--arm',arm,'--model',initial,'--label',arm+'-'+action,timeout=10800)
        return
    ROOT.mkdir(exist_ok=True);lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():print('Composition experiment complete');return
    status('verify_initial_q4_and_2048_backward')
    run('composition-v1/initial.log',SCRIPT+'compose_init.py')
    status('waiting_for_verified_teacher');started=time.monotonic()
    while not(ROOT/'teacher/manifest.json').exists():
        if time.monotonic()-started>7200:raise TimeoutError('Teacher did not complete')
        marker=json.loads((ROOT/'teacher-launch.json').read_text());proc=__import__('pathlib').Path('/proc')/str(marker['pid'])
        if not proc.exists():raise RuntimeError('Own teacher process ended before verified manifest: '+(ROOT/'teacher-controller.log').read_text()[-1200:])
        time.sleep(10)
    status('verify_all_training_references');run('composition-v1/prepare.log',SCRIPT+'compose_prepare.py',timeout=10800)
    initials={arm:ROOT/'initial'/arm for arm in ARMS};choices={};completed_phases=0
    # Extra phases are conditional on observed development, not the closed audit.
    for phase in range(1,5):
        status('matched_composition_training',course_phase=phase,steps_each=8000,arms=ARMS)
        parallel('train',phase,initials);reports={arm:json.loads((ROOT/f'{arm}-phase{phase}/training.json').read_text())for arm in ARMS}
        assert reports['champion']['actual_sample_counts']==reports['small']['actual_sample_counts']
        assert reports['champion']['optimizer_steps_by_context']==reports['small']['optimizer_steps_by_context']
        for arm,report in reports.items():
            record=next(x for x in report['history']if x['step']==report['best_step'])
            candidate={'model':container_path(ROOT/f'{arm}-phase{phase}/best'),'phase':phase,'step':report['best_step'],
                       'key':report['best_key'],'quality_gate':record['good_quality_gate'],'summary':record['summary']}
            if arm not in choices or candidate['key']>choices[arm]['key']:choices[arm]=candidate
        completed_phases=phase
        (ROOT/'selection-progress.json').write_text(json.dumps({'choices':choices,'fresh_opened':False},ensure_ascii=False,indent=2)+'\n')
        if any(c['quality_gate']for c in choices.values()):break
        if phase<4:
            status('training_only_feedback_collection',completed_course_phase=phase)
            target=ROOT/f'phase{phase+1}-feedback.jsonl'
            if not target.exists():
                parallel('feedback',phase)
                combined=[r for arm in ARMS for r in read(ROOT/f'feedback/{arm}-phase{phase}.jsonl')]
                random.Random(6113200+phase).shuffle(combined)
                save_jsonl(target,combined)
            initials={arm:ROOT/f'{arm}-phase{phase}/last'for arm in ARMS}
    winner=max(choices,key=lambda arm:(choices[arm]['key'],arm=='small'))
    selection={'choices':choices,'winner':winner,'fresh_used_for_selection':False,
               'rule':'formal>=95%, worst required parse/program rate, mean, long-context minimum; exact ties prefer smaller model',
               'frozen':json.loads((ROOT/'frozen.json').read_text()),'completed_phases':completed_phases}
    (ROOT/'preselected.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    status('closed_fresh_evaluation',winner_frozen=winner)
    parallel('final',0,{arm:c['model']for arm,c in choices.items()})
    parallel('baseline',0,{arm:ROOT/'initial'/arm for arm in ARMS})
    status('packaging_actual_evaluated_q4')
    run('composition-v1/export.log',SCRIPT+'compose_export.py')
    results={arm:json.loads((ROOT/f'results/{arm}-final.json').read_text())['summary']for arm in ARMS}
    (ROOT/'complete.json').write_text(json.dumps({'completed':True,'selected':winner,'completed_phases':completed_phases,
       'results':results,'fresh_used_for_selection':False,'native_device_measured':False},ensure_ascii=False,indent=2)+'\n')
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=str(error))
        raise
