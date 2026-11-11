"""Post-training error-kind probes and conflicts between diagnosis and DONE."""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from an_common import ROOT,ARMS,read,write


def score(arm):
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from am_model import Agent
    from an_eval import features
    from lowbit import load
    from ac_protocol import prompt_ids
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    aux=Agent(arm,checkpoint=ROOT/arm/'research.safetensors');folder=ROOT/'export'/(arm+'-research')
    model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True);load(model,folder/'model.mkqb');model.cuda().eval()
    tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True);report=json.loads((ROOT/arm/'research-fresh.json').read_text())
    tasks={t['id']:t for t in read(ROOT/'fresh-skills.jsonl')};rows=[]
    for r in report['skills']['details']:
        h=next((h for h in r['history']if'prompt'in h and'generation'in h),None)
        if h is None or len(prompt_ids(tokenizer,h['prompt']))>=1016:continue
        family=tasks[r['id']]['skill_family'];label=3 if r['initially_correct']else 1 if family in ['constant_binding','register_binding']else 2 if family=='power_pair'else 0
        rows.append({'prompt':h['prompt'],'label':label})
    h=features(model,tokenizer,[r['prompt']for r in rows]);pred=F.linear(h,aux.error_head.weight.detach().cpu(),aux.error_head.bias.detach().cpu()).argmax(-1)
    matrix=[[0]*5 for _ in range(5)]
    for r,p in zip(rows,pred.tolist()):matrix[r['label']][p]+=1
    decisions=[]
    for part,stats in report.items():
        for r in stats['details']:
            if not r['finished']:continue
            h=next((h for h in reversed(r['history'])if h.get('generation',{}).get('action')=='done'and'prompt'in h),None)
            if h and len(prompt_ids(tokenizer,h['prompt']))<1016:
                decisions.append({'prompt':h['prompt'],'correct':r['program_correct'],'panel':part})
    h=features(model,tokenizer,[r['prompt']for r in decisions]);pred=F.linear(h,aux.error_head.weight.detach().cpu(),aux.error_head.bias.detach().cpu()).argmax(-1).tolist()
    wrong=[p for r,p in zip(decisions,pred)if not r['correct']];good=[p for r,p in zip(decisions,pred)if r['correct']]
    result={'class_order':['operation','argument','composition','match','other'],
        'first_skill_states':{'total':len(rows),'correct':sum(matrix[i][i]for i in range(5)),'confusion_expected_rows_predicted_columns':matrix},
        'at_actual_DONE':{'wrong_total':len(wrong),'wrong_flagged_as_error':sum(p!=3 for p in wrong),'wrong_predicted_match':sum(p==3 for p in wrong),
            'correct_total':len(good),'correct_flagged_as_error':sum(p!=3 for p in good)},
        'diagnostic_only_not_runtime_gate':True,'optimizer_updates':0}
    write(ROOT/('error-type-'+arm+'.json'),result);print(json.dumps({'arm':arm,**result}),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['host','worker','model']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    if a.action=='model':score(a.arm);return
    if a.action=='worker':
        from run_experiment import run,SCRIPT
        run(f'hex-hypothesis-v2/error-type-{a.arm}.log',SCRIPT+'an_probe_errors.py','model','--arm',a.arm,timeout=3600);return
    assert(ROOT/'complete.json').exists()
    if(ROOT/'error-type-diagnostics.json').exists():return
    def worker(arm):
        env={**os.environ,'MK61_AGENT_GPU':'0'if arm=='direct'else'1'}
        subprocess.run([sys.executable,'-u',str(Path(__file__)),'worker','--arm',arm],env=env,check=True,stdout=subprocess.DEVNULL)
    with ThreadPoolExecutor(max_workers=2)as pool:list(pool.map(worker,ARMS))
    write(ROOT/'error-type-diagnostics.json',{arm:json.loads((ROOT/('error-type-'+arm+'.json')).read_text())for arm in ARMS})


if __name__=='__main__':main()
