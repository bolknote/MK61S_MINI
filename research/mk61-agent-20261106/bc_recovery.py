"""Development-only adapter-strength check; no SGD and no closed generations."""
import argparse
import json
import time
import torch
from safetensors.torch import load_file,save_file
from bc_common import ROOT,HERE,read,write,sha,check_frozen,output_ids,compact_head
from bc_model import Agent
from bc_eval import evaluate,key,brief

def main(run):
    check_frozen();assert not(ROOT/'preselected.json').exists()
    policy=read(ROOT/'recovery-policy.json');assert policy['closed_opened']is False
    assert sha(HERE/'bc_recovery.py')==policy['source_sha256']
    assert all((ROOT/n/'training.json').exists()for n in ['seed-a','seed-b'])
    out=ROOT/run
    if(out/'recovery-complete.json').exists():return
    parent=load_file(ROOT/'parent.safetensors');trained=load_file(out/'step-4000.safetensors');assert set(parent)==set(trained)
    reference=read(ROOT/'parent-development.json');best=read(out/'best.json')
    if not(out/'best-before-recovery.json').exists():
        write(out/'best-before-recovery.json',best)
        (out/'best-before-recovery.safetensors').write_bytes((out/'best.safetensors').read_bytes())
    results=[]
    for alpha in policy['alphas']:
        tag=str(alpha).replace('.','p');checkpoint=out/('blend-'+tag+'.safetensors')
        weights={n:((1-alpha)*parent[n]+alpha*trained[n]).contiguous()for n in parent};save_file(weights,checkpoint)
        agent=Agent(checkpoint=checkpoint);replica,_=agent.packed(out/('blend-'+tag+'.mkqb'))
        replica.cuda().eval();compact_head(replica,output_ids(agent.tokenizer));report=evaluate(replica,agent.tokenizer,'development');score=key(report,reference)
        write(out/('recovery-'+tag+'.json'),report)
        if score>best['key']:
            agent.save_checkpoint(out/'best.safetensors');best={'step':4000,'recovery_alpha':alpha,'recovery':'parameter interpolation of continued rank16 factors and action rows',
                'key':score,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
        results.append({'alpha':alpha,'key':score});write(out/'recovery-status.json',{'completed':results,'best':best})
        print(json.dumps({'run':run,'alpha':alpha,'key':score,'development':brief(report)}),flush=True)
        del replica,agent;torch.cuda.empty_cache();check_frozen()
    write(out/'recovery-complete.json',{'results':results,'optimizer_updates':0,'closed_opened':False,'best':best,'unix':time.time()})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',choices=['seed-a','seed-b'],required=True);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;main(a.run)
