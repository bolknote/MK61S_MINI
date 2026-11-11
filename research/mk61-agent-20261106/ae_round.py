"""Run both authorized B200 arms through the complete frozen three-stage course."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from ae_common import ROOT,HERE,ARMS,read,write,sha,INITIAL_PACKET,COMPILER_PACKET
from run_experiment import REPO,SCRIPT,run
from tasks import save_jsonl


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action,block):
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'ae_round.py','worker',arm,action,str(block)],cwd=REPO,
           env={**os.environ,'MK61_AGENT_GPU':'1'if arm in ['full','initial']else'0'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(f'Semantic training worker failed: {arm}/{action}/{block}')


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
        args=[SCRIPT+'ae_train.py','--arm',arm,'--block',block]if action=='train'else[SCRIPT+'ae_jobs.py','--action',action,'--arm',arm,'--block',block]
        run(f'semantic-debug-v2/{arm}-{action}.log',*args,timeout=28800);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    assert(ROOT/'data-frozen.json').exists();policy=json.loads((ROOT/'policy.json').read_text())
    status('preflight');run('semantic-debug-v2/preflight.log',SCRIPT+'ae_prepare.py',timeout=7200)
    status('semantic_head_warmup_and_initial_baseline')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,'warmup','train',0),pool.submit(worker,'initial','baseline',0)]):f.result()
    status('initial_student_mining');worker('warmup','mine',0);union(0,['warmup'])
    for block in range(1,policy['blocks']+1):
        status('paired_SFT',block=block,blocks=policy['blocks']);parallel('train',block)
        reports={a:json.loads((ROOT/a/f'training-{block}.json').read_text())for a in ARMS}
        assert reports['lora16']['same_draw_digest']==reports['full']['same_draw_digest']
        assert reports['lora16']['counts']==reports['full']['counts']
        if block<policy['blocks']:
            status('verified_student_repair_refresh',block=block);parallel('mine',block);union(block,ARMS)
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS};selected=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'choices':choices,'selected_arm':selected,'release_eligible':choices[selected]['key'][0],
        'fresh_used_for_selection':False,'correctness_thresholds_fixed_on_development':True})
    status('initial_on_same_fresh_exam');worker('initial','baseline',0)
    status('sealed_fresh_exam');parallel('audit',0)
    status('exporting');run('semantic-debug-v2/export.log',SCRIPT+'ae_export.py',timeout=7200)
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    assert sha(INITIAL_PACKET)==frozen['initial_tool_packet_sha256']and sha(COMPILER_PACKET)==frozen['compiler_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'warmup_updates':policy['warmup_steps'],
        'updates_per_arm':policy['blocks']*policy['steps_per_block'],'initial_models_unchanged':True})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2:status('failed',error=repr(error))
        raise
