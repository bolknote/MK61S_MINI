"""Additional fixed-budget comparison; never changes the preselected models."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import json
import os
import subprocess
import sys
import time
from ap_common import ROOT,HERE,ARMS,ACTIONS,ACTION_IDS,CORRECT_IDS,output_ids,compact_head,write,sha,read
from run_experiment import REPO,SCRIPT,run


def audit(arm):
    import torch
    from ap_model import Agent
    from ap_eval import evaluate,generate
    from ap_runtime import render
    from aj_teacher import correct
    from full_isa_vm import FullVM
    from ap_protocol import header_ids
    from native_quant import attach,export
    policy=json.loads((ROOT/'policy.json').read_text());step=policy['steps'];checkpoint=ROOT/arm/f'step-{step}.safetensors'
    agent=Agent(checkpoint=checkpoint);folder=ROOT/'export'/(arm+'-terminal');folder.mkdir(parents=True,exist_ok=True)
    model,_=agent.packed(folder/'model.mkqb');model.cuda().eval();compact_head(model,output_ids(agent.tokenizer))
    # Probe an observed train/runtime difference on development only. Empty
    # goal lessons inherited budget 10, whereas real new sessions start at 12.
    groups=read(ROOT/'development.jsonl')[:32];vm=FullVM();sensitivity={}
    for budget in [10,12]:
        prompts=[]
        for g in groups:
            state={**g['rows'][3]['state'],'body':None,'runs':{},'diagnosis':None,'remaining':budget}
            prompts.append(render(state,arm))
        outputs=generate(model,agent.tokenizer,prompts)
        sensitivity[str(budget)]={'total':len(outputs),'write_actions':sum(g['action']=='write'for g in outputs),
          'correct_programs':sum(v['action']=='write'and correct(vm,g['task'],v['body'],g['task']['constants'])for g,v in zip(groups,outputs))}
    write(ROOT/arm/'development-budget-sensitivity.json',sensitivity)
    write(ROOT/arm/'terminal-fresh.json',evaluate(model,agent.tokenizer,'fresh',arm))
    master=agent.merged_master();master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf')
    attach(master,'q4');export(master,folder/'model.mkqb','q4')
    write(folder/'output-token-ids.json',output_ids(agent.tokenizer));write(folder/'protocol.json',{'kind':'mk61-step-debug-v1','format_arm':arm,'actions':ACTIONS,
      'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,'context':1024,'neural_headers':{a:header_ids(agent.tokenizer,a)for a in ['write','run','diag']},
      'external_semantic_veto':False,'additional_fixed_endpoint_analysis':True})
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','parameter_count':3022080,'packed_sha256':sha(folder/'model.mkqb'),
      'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'step':step,'checkpoint_sha256':sha(checkpoint),
      'additional_fixed_endpoint_analysis':True,'not_used_for_selection':True})


def worker(arm):
    if(ROOT/arm/'terminal-fresh.json').exists()and(ROOT/'export'/(arm+'-terminal')/'manifest.json').exists():return
    p=subprocess.run([sys.executable,'-u',SCRIPT+'step_endpoint_audit.py',arm],cwd=REPO,
      env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='full'else'1'})
    if p.returncode:raise RuntimeError((arm,p.returncode))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['host','full','short']);a=ap.parse_args()
    if a.action=='host':
        lock=(ROOT/'endpoint.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert(ROOT/'complete.json').exists()and(ROOT/'preselected.json').exists()
        selection=sha(ROOT/'preselected.json');write(ROOT/'endpoint-start.json',{'unix':time.time(),'primary_exam_already_opened':True,
          'endpoint_from_fixed_training_budget':True,'optimizer_updates':0,'not_used_for_selection':True})
        with ThreadPoolExecutor(max_workers=2)as pool:
            for f in as_completed([pool.submit(worker,arm)for arm in ARMS]):f.result()
        assert sha(ROOT/'preselected.json')==selection
        write(ROOT/'endpoint-complete.json',{'complete':True,'optimizer_updates':0,'not_used_for_selection':True,
          'script_sha256':sha(HERE/'step_endpoint_audit.py'),'preselection_unchanged':True});return
    if os.environ.get('MK61_ENDPOINT_CONTAINER')=='1':
        import torch
        torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;audit(a.action)
    else:
        # Keep the same offline container and GPU isolation as the primary run.
        run(f'step-debug-v1/{a.action}-endpoint.log',SCRIPT+'step_endpoint_audit.py',a.action,'--container',timeout=14400)


if __name__=='__main__':
    if '--container'in sys.argv:
        sys.argv.remove('--container');os.environ['MK61_ENDPOINT_CONTAINER']='1'
    main()
