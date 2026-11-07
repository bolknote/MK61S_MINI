"""Bounded complete experiment; two cards, common on-policy pools, sealed exam."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from ab_common import ROOT,HERE,INITIAL,INITIAL_PACKET,ARMS,read,write,sha
from run_experiment import REPO,SCRIPT,run
from tasks import save_jsonl


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def worker(arm,action,stage):
    with(ROOT/(arm+'-'+action+'-controller.log')).open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'ab_round.py','worker',arm,action,str(stage)],cwd=REPO,
                              env={**os.environ,'MK61_AGENT_GPU':'1'if arm in ['preference','baseline']else'0'},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Action experiment worker failed: '+arm+' '+action)


def parallel(action,stage):
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,a,action,stage)for a in ARMS]):f.result()


def union(stage,arms):
    if(ROOT/f'onpolicy-union-{stage}.jsonl').exists():return
    rows=[];seen=set();sources={}
    # Include prior pools, so each refresh does not erase previous failures.
    previous=ROOT/f'onpolicy-union-{stage-1}.jsonl'
    values=read(previous)if previous.exists()else[]
    for arm in arms:
        p=ROOT/f'onpolicy-{stage}-{arm}.jsonl';values+=read(p);sources[p.name]=sha(p)
    for row in values:
        key=(row['prompt'],row['action'],tuple(row['body']))
        if key in seen:continue
        seen.add(key);rows.append(row)
    save_jsonl(ROOT/f'onpolicy-union-{stage}.jsonl',rows)
    write(ROOT/f'onpolicy-frozen-{stage}.json',{'rows':len(rows),'sources':sources,
            'sha256':sha(ROOT/f'onpolicy-union-{stage}.jsonl'),'train_only':True,
            'unique_actual_false_DONE':sum(bool(r.get('actual_false_DONE'))for r in rows)})


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,action,stage=sys.argv[2:5]
        args=[SCRIPT+'ab_train.py','--arm',arm,'--stage',stage]if action=='train'else[SCRIPT+'ab_eval.py','--action',action,'--arm',arm,'--stage',stage]
        run(f'action-alignment-v2/{arm}-{action}.log',*args,timeout=21600);return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(ROOT/'complete.json').exists():return
    if not(ROOT/'data-frozen.json').exists():
        status('preparing_data');run('action-alignment-v2/data.log',SCRIPT+'ab_data.py',timeout=14400)
    data=json.loads((ROOT/'data-frozen.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    status('preflight');run('action-alignment-v2/preflight.log',SCRIPT+'ab_prepare.py',timeout=3600)
    status('shared_format_warmup_and_original_baseline')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in as_completed([pool.submit(worker,'warmup','train',0),pool.submit(worker,'baseline','baseline',0)]):f.result()
    status('initial_on_policy_refresh');worker('warmup','mine',0);union(0,['warmup'])
    for stage in range(1,policy['stages']+1):
        status('paired_training',stage=stage,stages=policy['stages']);parallel('train',stage)
        reports={a:json.loads((ROOT/a/f'training-stage-{stage}.json').read_text())for a in ARMS}
        assert reports['sft']['sample_plan_digest']==reports['preference']['sample_plan_digest']
        assert reports['sft']['counts']==reports['preference']['counts']
        if stage<policy['stages']:
            status('refreshing_current_students',stage=stage);parallel('mine',stage);union(stage,ARMS)
    choices={a:json.loads((ROOT/a/'best.json').read_text())for a in ARMS}
    chosen=max(ARMS,key=lambda a:choices[a]['key'])
    write(ROOT/'preselected.json',{'choices':choices,'selected_arm':chosen,'release_eligible':choices[chosen]['key'][0],
                                 'fresh_used_for_selection':False,'policy_sha256':sha(ROOT/'policy.json')})
    status('sealed_fresh_exam');parallel('audit',0)
    status('exporting');run('action-alignment-v2/export.log',SCRIPT+'ab_export.py',timeout=3600)
    assert sha(INITIAL/'model.safetensors')==data['initial_master_sha256']and sha(INITIAL_PACKET)==data['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'warmup_updates':policy['format_warmup_steps'],
                              'updates_each':policy['steps_per_stage']*policy['stages'],'source_unchanged':True})
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=repr(error))
        raise
