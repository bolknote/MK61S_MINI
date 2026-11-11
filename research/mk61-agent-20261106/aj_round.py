"""Bounded adapter continuation and a fresh ROM-backed exam on both B200s."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from aj_common import ROOT,HERE,ARMS,START,START_PACKET,read,write,sha,INITIAL_PACKET,COMPILER_PACKET
from run_experiment import REPO,SCRIPT,run
from tasks import save_jsonl


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action,block):
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'aj_round.py','worker',arm,action,str(block)],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':'1'if arm in ['lr10','initial']else'0'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(f'Targeted adapter worker failed: {arm}/{action}/{block}')


def parallel(action,block):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action,block)for a in ARMS]):f.result()


def union(block,arms):
    path=ROOT/f'onpolicy-union-{block}.jsonl'
    if path.exists():return
    previous=ROOT/f'onpolicy-union-{block-1}.jsonl';rows=read(previous)if previous.exists()else[]
    for arm in arms:rows+=read(ROOT/f'onpolicy-{block}-{arm}.jsonl')
    seen=set();unique=[]
    for row in rows:
        key=json.dumps([row['prompt'],row['action'],row['body'],row['correctness']],ensure_ascii=False)
        if key in seen:continue
        seen.add(key);unique.append(row)
    save_jsonl(path,unique);write(ROOT/f'onpolicy-frozen-{block}.json',{'rows':len(unique),'sha256':sha(path),'training_only':True})


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action,block=sys.argv[2:5]
        args=[SCRIPT+'aj_train.py','--arm',arm,'--block',block]if action=='train'else[SCRIPT+'aj_jobs.py','--action',action,'--arm',arm,'--block',block]
        run(f'completion-retention-v2/{arm}-{action}.log',*args,timeout=28800);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    policy=json.loads((ROOT/'policy.json').read_text());status('preflight');run('completion-retention-v2/preflight.log',SCRIPT+'aj_prepare.py',timeout=7200)
    status('initial_development_and_error_mining')
    with ThreadPoolExecutor(max_workers=2)as pool:
        # Initial mining is serial after baseline: it uses the newly frozen threshold.
        pool.submit(worker,'initial','baseline',0).result()
    initial=json.loads((ROOT/'initial-development-audit.json').read_text())
    for arm in ARMS:
        out=ROOT/arm;out.mkdir(exist_ok=True)
        if not(out/'best.json').exists():
            shutil.copyfile(START,out/'best.safetensors');write(out/'best.json',{'block':0,'key':initial['key'],'threshold':initial['threshold'],'release_eligible':initial['release_eligible'],'sha256':sha(START)})
    if not(ROOT/'onpolicy-union-0.jsonl').exists():worker('initial','mine',0);union(0,['initial'])
    for block in range(1,policy['blocks']+1):
        status('paired_adapter_training',block=block,blocks=policy['blocks']);parallel('train',block)
        reports={a:json.loads((ROOT/a/f'training-{block}.json').read_text())for a in ARMS}
        assert reports[ARMS[0]]['same_draw_digest']==reports[ARMS[1]]['same_draw_digest']
        assert reports[ARMS[0]]['counts']==reports[ARMS[1]]['counts']
        if block<policy['blocks']:
            if block in policy['mining_blocks']:
                status('verified_student_error_refresh',block=block);parallel('mine',block);union(block,ARMS)
            else:union(block,[])
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS};selected=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'choices':choices,'selected_arm':selected,'release_eligible':choices[selected]['release_eligible'],
       'fresh_used_for_selection':False,'correctness_thresholds_fixed_on_development':True,'starting_adapter_retained_if_no_improvement':True,
       'all_four_panels_nonregressing_on_success_false_DONE_and_correct_starts':choices[selected]['key'][0]})
    status('initial_on_same_fresh_exam');worker('initial','baseline',0)
    status('sealed_fresh_exam');parallel('audit',0)
    status('exporting');run('completion-retention-v2/export.log',SCRIPT+'aj_export.py',timeout=7200)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    assert sha(START)==frozen['start_checkpoint_sha256']and sha(START_PACKET)==frozen['start_packet_sha256']
    assert sha(INITIAL_PACKET)==frozen['initial_tool_packet_sha256']and sha(COMPILER_PACKET)==frozen['compiler_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'updates_per_arm':policy['blocks']*policy['steps_per_block'],'initial_models_unchanged':True});status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2:status('failed',error=repr(error))
        raise
