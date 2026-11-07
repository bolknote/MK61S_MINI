"""Coordinate four independent Q4 variants on two complete B200s."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
import subprocess
import sys
import time

from codec_common import ROOT,ARMS,MODES,sha
from run_experiment import REPO,SCRIPT,run


def status(phase,**extra):
    value={'phase':phase,'unix':time.time(),**extra};(ROOT/'status.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)


def worker(arm,mode,action):
    gpu=ARMS.index(arm);name=arm+'-'+mode+'-'+action
    with(ROOT/(name+'-controller.log')).open('a')as log:
        result=subprocess.run([sys.executable,'-u',SCRIPT+'codec_round.py','worker',arm,mode,action],cwd=REPO,
          env={**os.environ,'MK61_AGENT_GPU':str(gpu)},stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Own worker failed: '+name)


def prepare():
    if(ROOT/'resources.json').exists():return
    status('equal_initialization_and_full_gpu_preflight')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in [pool.submit(worker,arm,'h32','init')for arm in ARMS]:f.result()
    manifests={arm:json.loads((ROOT/'initial'/arm/'manifest.json').read_text())for arm in ARMS}
    resources={'effective_batch':128,'memory_fraction_each':.45,'micro_by_context':{str(c):min(x['micro_bounds'][str(c)]for x in manifests.values())for c in [512,1024,2048]},
      'workers_each_gpu':2,'gpu_assignment':{'champion-hex':0,'champion-h32':0,'small-hex':1,'small-h32':1},
      'source_initialization_sha256':{arm:sha(ROOT/'initial'/arm/'manifest.json')for arm in ARMS},'before_any_optimizer_updates':True}
    assert json.loads((ROOT/'policy.json').read_text())['effective_batch']==resources['effective_batch']
    assert all(resources['effective_batch']%n==0 for n in resources['micro_by_context'].values())
    (ROOT/'resources.json').write_text(json.dumps(resources,indent=2)+'\n');status('preflight_complete',resources=resources)


def main():
    ROOT.mkdir(exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        arm,mode,action=sys.argv[2:5]
        if action=='init':run('codec-qat-v1/init-'+arm+'.log',SCRIPT+'codec_init.py','--arm',arm,timeout=10800)
        elif action=='train':run('codec-qat-v1/'+arm+'-'+mode+'.log',SCRIPT+'codec_train.py','--arm',arm,'--mode',mode,timeout=21600)
        elif action in ['endpoint','best','baseline']:
            label=arm+'-'+mode+'-'+action;path=ROOT/'results'/(label+'.json')
            if path.exists():return
            if action=='baseline':source=ROOT/'initial'/arm/'hf'
            else:source=ROOT/(arm+'-'+mode)/('last'if action=='endpoint'else'best')
            relative=str(source.relative_to(REPO))
            run('codec-qat-v1/'+label+'.log',SCRIPT+'codec_eval.py','--arm',arm,'--mode',mode,'--model',relative,'--label',label,timeout=10800)
        else:raise ValueError(action)
        return
    lock=(ROOT/'controller.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if len(sys.argv)>1 and sys.argv[1]=='prepare':prepare();return
    if(ROOT/'complete.json').exists():print('Codec comparison complete');return
    prepare();status('four_parallel_codec_trainings',steps_each=8000,effective_batch=128)
    with ThreadPoolExecutor(max_workers=4)as pool:
        for f in [pool.submit(worker,arm,mode,'train')for arm in ARMS for mode in MODES]:f.result()
    reports={arm+'-'+mode:json.loads((ROOT/(arm+'-'+mode)/'training.json').read_text())for arm in ARMS for mode in MODES}
    first=next(iter(reports.values()))
    for report in reports.values():
        assert report['sample_plan_digest']==first['sample_plan_digest']
        assert report['actual_sample_counts']==first['actual_sample_counts']
        assert report['optimizer_steps_by_context']==first['optimizer_steps_by_context']
    choices={name:{'endpoint':'last','endpoint_step':report['steps'],'best_step':report['best_step'],'best_key':report['best_key'],
      'endpoint_master_sha256':sha(ROOT/name/'last/model.safetensors'),'best_master_sha256':sha(ROOT/name/'best/model.safetensors')}for name,report in reports.items()}
    selection={'choices':choices,'primary_comparison':'Fixed8000-update endpoints','secondary_comparison':'Best observed validation checkpoint',
      'new_fresh_used_for_selection':False,'sample_plan_digests_equal_across_all_four':True,'frozen_sha256':sha(ROOT/'frozen.json')}
    (ROOT/'preselected.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    status('new_closed_audit_endpoints')
    with ThreadPoolExecutor(max_workers=4)as pool:
        for f in [pool.submit(worker,arm,mode,'endpoint')for arm in ARMS for mode in MODES]:f.result()
    status('new_closed_audit_validation_best')
    with ThreadPoolExecutor(max_workers=4)as pool:
        for f in [pool.submit(worker,arm,mode,'best')for arm in ARMS for mode in MODES]:f.result()
    status('unchanged_initial_baselines')
    with ThreadPoolExecutor(max_workers=2)as pool:
        for f in [pool.submit(worker,arm,'hex','baseline')for arm in ARMS]:f.result()
    status('exporting_actual_audited_packets')
    run('codec-qat-v1/export.log',SCRIPT+'codec_export.py',timeout=3600)
    (ROOT/'complete.json').write_text(json.dumps({'completed':True,'new_fresh_used_for_selection':False,'steps_each':8000,
      'effective_batch':128,'variants':list(choices),'primary_endpoint_fixed':True,'native_picocalc_measured':False},indent=2)+'\n')
    status('complete')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if len(sys.argv)<2 or sys.argv[1]!='worker':status('failed',error=str(error))
        raise
