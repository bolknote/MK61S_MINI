"""Continue identical existing rank16 weights with matched draws on two B200s."""
import argparse
import json
import math
import time
import torch
from ag_common import ROOT,HERE,ARMS,START,body_ids,output_ids,compact_head,write,sha
from ag_model import Agent
from ag_course import Course,loss
from ag_eval import development,brief


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);ap.add_argument('--block',type=int,required=True);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(913501);torch.cuda.set_per_process_memory_fraction(.85);torch.backends.cuda.matmul.allow_tf32=False
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    out=ROOT/a.arm;out.mkdir(exist_ok=True);record=out/f'training-{a.block}.json'
    if record.exists():return
    model=Agent(a.arm,checkpoint=out/'last.safetensors'if a.block>1 else START);original=model.input_digest()
    base=[p for n,p in model.named_parameters()if p.requires_grad and n not in ['action_head','correct_head']]
    groups=[{'params':base,'lr_base':policy['lr_lora'],'weight_decay':.01},
        {'params':[model.action_head],'lr_base':policy['lr_action'],'weight_decay':0.},
        {'params':[model.correct_head],'lr_base':policy['lr_correct'],'weight_decay':0.}]
    optimizer=torch.optim.AdamW(groups)
    if a.block>1:optimizer.load_state_dict(torch.load(out/'optimizer.pt',weights_only=True,map_location='cuda'))
    course=Course(model.tokenizer,a.block);head=torch.tensor(body_ids(model.tokenizer),device='cuda');steps=policy['steps_per_block'];started=time.monotonic();losses=[]
    for step in range(1,steps+1):
        model.train();optimizer.zero_grad(set_to_none=True);factor=min(1.,step/50)*(.5+.5*(1+math.cos(math.pi*step/steps))/2)
        for group in optimizer.param_groups:group['lr']=group['lr_base']*factor
        batch=course.batch(step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):
            value,parts=loss(model,batch,head,policy)
        if not torch.isfinite(value):raise RuntimeError('Nonfinite targeted loss')
        value.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%25==0:
            state={'phase':'training','arm':a.arm,'block':a.block,'step':step,'steps':steps,'loss_last25':sum(losses[-25:])/len(losses[-25:]),'components':parts,'seconds':time.monotonic()-started};write(out/'status.json',state)
            if step%100==0:print(json.dumps(state),flush=True)
    assert model.input_digest()==original
    model.save_checkpoint(out/'last.safetensors');torch.save(optimizer.state_dict(),out/'optimizer.pt')
    replica,packed=model.packed(out/f'block-{a.block}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
    result=development(replica,model.tokenizer);write(out/f'development-{a.block}.json',result);key=result['key']
    best=json.loads((out/'best.json').read_text())if(out/'best.json').exists()else None
    if best is None or key>best['key']:
        model.save_checkpoint(out/'best.safetensors');write(out/'best.json',{'block':a.block,'key':key,'threshold':result['threshold'],'sha256':sha(out/'best.safetensors')})
    write(record,{'arm':a.arm,'block':a.block,'steps':steps,'trainable_parameters':model.trainable_count(),'input_embedding_bit_identical':True,
        'input_digest':original,'same_draw_digest':course.digest,'counts':dict(course.counts),'summary':brief(result),
        'Q4_merged_every_forward':True,'seconds':time.monotonic()-started,'packed':packed})
    write(out/'status.json',{'phase':'complete_block','block':a.block,'steps':steps,'key':key})
    print(json.dumps({'arm':a.arm,'block':a.block,'summary':brief(result)}),flush=True)


if __name__=='__main__':main()
