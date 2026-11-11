"""Complete four-block curriculum with paired SFT/outcome training on two B200s."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from ac_common import ROOT,HERE,INITIAL,INITIAL_PACKET,ARMS,read,write,sha
from run_experiment import REPO,SCRIPT,run
from tasks import save_jsonl


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def advance(result):
    t=result['tools']['simple']
    return t['false_DONE']==0 and t['repaired']/max(1,t['initially_wrong'])>=.9 and t['correct_controls_completed']/max(1,t['correct_controls'])>=.95


def worker(arm,action,block):
    with(ROOT/f'{arm}-{action}-controller.log').open('a')as log:
        p=subprocess.run([sys.executable,'-u',SCRIPT+'ac_round.py','worker',arm,action,str(block)],cwd=REPO,
                         env={**os.environ,'MK61_AGENT_GPU':'1'if arm in ['outcome','baseline']else'0'},stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(f'Adapter worker failed: {arm}/{action}/{block}')


def parallel(action,block):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action,block)for a in ARMS]):f.result()


def union(block,arms):
    for source,prefix in [('onpolicy','onpolicy'),('preferences','preference')]:
        target=ROOT/f'{prefix}-union-{block}.jsonl'
        if target.exists():continue
        values=[];previous=ROOT/f'{prefix}-union-{block-1}.jsonl'
        if previous.exists():values+=read(previous)
        for arm in arms:values+=read(ROOT/f'{source}-{block}-{arm}.jsonl')
        rows=[];seen=set()
        for row in values:
            key=json.dumps([row['prompt'],row['action'],row['body']],ensure_ascii=False)if source=='onpolicy'else json.dumps([row['chosen'],row['rejected']],ensure_ascii=False)
            if key in seen:continue
            seen.add(key);rows.append(row)
        save_jsonl(target,rows)
        write(ROOT/f'{prefix}-frozen-{block}.json',{'rows':len(rows),'sha256':sha(target),'training_only':True})


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action,block=sys.argv[2:5]
        args=[SCRIPT+'ac_train.py','--arm',arm,'--block',block]if action=='train'else[SCRIPT+'ac_eval.py','--action',action,'--arm',arm,'--block',block]
        run(f'debug-adapter-v2/{arm}-{action}.log',*args,timeout=21600);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    if not(ROOT/'data-frozen.json').exists():run('debug-adapter-v2/data.log',SCRIPT+'ac_data.py',timeout=14400)
    policy=json.loads((ROOT/'policy.json').read_text());data=json.loads((ROOT/'data-frozen.json').read_text())
    status('preflight');run('debug-adapter-v2/preflight.log',SCRIPT+'ac_prepare.py',timeout=7200)
    status('head_warmup_and_baseline')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,'warmup','train',0),pool.submit(worker,'baseline','baseline',0)]):f.result()
    write(ROOT/'level-0.json',{'level':1});status('initial_student_candidates');worker('warmup','mine',0);union(0,['warmup'])
    level=1
    for block in range(1,policy['blocks']+1):
        write(ROOT/f'level-{block}.json',{'level':level,'fresh_used':False})
        status('paired_adapter_training',block=block,blocks=policy['blocks'],level=level);parallel('train',block)
        reports={a:json.loads((ROOT/a/f'training-{block}.json').read_text())for a in ARMS}
        assert reports['sft']['sample_plan_digest']==reports['outcome']['sample_plan_digest']
        assert reports['sft']['SFT_counts']==reports['outcome']['SFT_counts']
        advances={a:advance(json.loads((ROOT/a/f'development-{block}.json').read_text()))for a in ARMS}
        write(ROOT/f'curriculum-gate-{block}.json',{'level':level,'arms_pass':advances,'advanced':all(advances.values()),'fresh_used':False})
        if all(advances.values()):level=2
        if block<policy['blocks']:
            status('refreshing_full_episode_preferences',block=block);parallel('mine',block);union(block,ARMS)
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS};chosen=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'choices':choices,'selected_arm':chosen,'release_eligible':choices[chosen]['key'][0],
                                 'highest_curriculum_level':level,'fresh_used_for_selection':False})
    status('sealed_fresh_exam');parallel('audit',0)
    status('exporting');run('debug-adapter-v2/export.log',SCRIPT+'ac_export.py',timeout=7200)
    assert sha(INITIAL/'model.safetensors')==data['initial_master_sha256']and sha(INITIAL_PACKET)==data['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'warmup_updates':policy['warmup_steps'],
                              'updates_each':policy['blocks']*policy['steps_per_block'],'base_unchanged':True})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as e:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(e))
        raise
