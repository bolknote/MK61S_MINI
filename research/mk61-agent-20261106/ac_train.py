"""Freeze every base parameter; update only tool-role LoRA and its action head."""
import argparse
import json
import math
import time
import torch
from ac_common import ROOT,HERE,read,write,sha,body_ids,output_ids,compact_head
from ac_model import Agent
from ac_course import Course,supervised_loss,trajectory_dpo
from ac_eval import development,selection,brief


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['warmup','sft','outcome'],required=True);ap.add_argument('--block',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(811412);torch.cuda.set_per_process_memory_fraction(.85)
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    out=ROOT/a.arm;out.mkdir(exist_ok=True);record_path=out/f'training-{a.block}.json'
    if record_path.exists():return
    checkpoint=None if a.arm=='warmup'else ROOT/'warmup/last.safetensors'if a.block==1 else out/'last.safetensors'
    model=Agent(checkpoint=checkpoint);tokenizer=model.tokenizer;original=model.frozen_digest()
    lora=[p for n,p in model.named_parameters()if p.requires_grad and n!='action_head']
    optimizer=torch.optim.AdamW([{'params':lora,'factor':0. if a.arm=='warmup'else 1.,'weight_decay':.01},
                                {'params':[model.action_head],'factor':1.,'weight_decay':0.}],lr=policy['lr'])
    if a.block>1:optimizer.load_state_dict(torch.load(out/'optimizer.pt',weights_only=True,map_location='cuda'))
    reference=Agent(checkpoint=ROOT/'warmup/last.safetensors').requires_grad_(False).eval()if a.arm=='outcome'else None
    level=1 if a.arm=='warmup'else json.loads((ROOT/f'level-{a.block}.json').read_text())['level']
    course=Course(tokenizer,a.block,level);head=torch.tensor(body_ids(tokenizer),device='cuda')
    steps=policy['warmup_steps']if a.arm=='warmup'else policy['steps_per_block'];losses=[];started=time.monotonic()
    for step in range(1,steps+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=policy['lr']*min(1.,step/40)*(.5+.5*(1+math.cos(math.pi*step/steps))/2)
        for group in optimizer.param_groups:group['lr']=rate*group['factor']
        batch=course.batch(step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):loss,parts=supervised_loss(model,batch,head)
        if not torch.isfinite(loss):raise RuntimeError('Nonfinite supervised loss')
        loss.backward();total=float(loss.detach());del loss,batch
        if reference is not None:
            pairs=course.preferences(policy['pref_pairs_per_update'],'cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):pref=trajectory_dpo(model,reference,pairs,head,policy['dpo_beta'])
            if not torch.isfinite(pref):raise RuntimeError('Nonfinite trajectory preference loss')
            (policy['dpo_weight']*pref).backward();parts['full_trajectory_DPO']=float(pref.detach());total+=policy['dpo_weight']*parts['full_trajectory_DPO']
            del pairs,pref
        if a.arm=='warmup':
            for p in lora:p.grad=None
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(total)
        if step==1 or step%25==0:
            status={'phase':'training','arm':a.arm,'block':a.block,'level':level,'step':step,'steps':steps,
                    'loss_last25':sum(losses[-25:])/len(losses[-25:]),'components':parts,'seconds':time.monotonic()-started}
            write(out/'status.json',status)
            if step%100==0:print(json.dumps(status),flush=True)
    assert model.frozen_digest()==original
    model.save_adapter(out/'last.safetensors');torch.save(optimizer.state_dict(),out/'optimizer.pt')
    replica,packed=model.packed(out/f'block-{a.block}.mkqb');replica.to('cuda').eval();compact_head(replica,output_ids(tokenizer))
    torch.backends.cuda.matmul.allow_tf32=False
    result=development(replica,tokenizer);key=selection(result);write(out/f'development-{a.block}.json',result)
    best=json.loads((out/'best.json').read_text())if(out/'best.json').exists()else None
    if best is None or key>best['key']:
        model.save_adapter(out/'best.safetensors');write(out/'best.json',{'block':a.block,'key':key,'adapter_sha256':sha(out/'best.safetensors')})
    counts={k:v for k,v in course.counts.items()if k!='preference_paths'}
    write(record_path,{'arm':a.arm,'block':a.block,'level':level,'steps':steps,'sample_plan_digest':course.digest,'SFT_counts':counts,
          'preference_paths':course.counts['preference_paths'],'base_frozen_digest':original,'base_bit_identical':True,
          'trainable_parameters':18560,'rank':4,'key':key,'summary':brief(result),'packed':packed,
          'Q4_merged_forward_from_first_update':True,'seconds':time.monotonic()-started,
          'preference_scope':'whole actual execution trajectories'if reference is not None else None})
    write(out/'status.json',{'phase':'complete_block','block':a.block,'level':level,'steps':steps,'key':key})
    print(json.dumps({'arm':a.arm,'block':a.block,'key':key,'metrics':brief(result)}),flush=True)


if __name__=='__main__':main()
