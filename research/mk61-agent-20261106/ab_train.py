"""Shared format warmup, then paired SFT / SFT+action-DPO with Q4 from update 1."""
import argparse
import hashlib
import json
import math
import time
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from ab_common import ROOT,INITIAL,HERE,ACTION_IDS,read,write,sha,body_ids,output_ids,compact_head
from ab_course import Course,separate_loss,preference_loss
from ab_eval import development,selection,brief
from native_quant import attach,save,packed_copy


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['warmup','sft','preference'],required=True)
    ap.add_argument('--stage',type=int,default=0);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(712412);torch.cuda.set_per_process_memory_fraction(.8)
    torch.backends.cuda.matmul.allow_tf32=True
    policy=json.loads((ROOT/'policy.json').read_text());frozen=json.loads((ROOT/'prepared.json').read_text())
    for n,d in frozen['source_hashes'].items():assert sha(HERE/n)==d,n
    out=ROOT/a.arm;out.mkdir(exist_ok=True)
    result_path=out/f'training-stage-{a.stage}.json'
    if result_path.exists():return
    source=INITIAL if a.arm=='warmup'else ROOT/'warmup/last'if a.stage==1 else out/'last'
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True).to('cuda')
    if a.arm=='warmup':
        # Existing unused rows, no vocabulary/parameter-count growth.
        with torch.no_grad():
            weight=model.get_input_embeddings().weight
            for target,letter in zip(ACTION_IDS,['w','p','r','t','t','d','u']):
                weight[target].copy_(weight[tokenizer.encode(letter,add_special_tokens=False)[0]])
    attach(model,'q4');embedding=model.get_input_embeddings().parametrizations.weight.original
    if a.arm=='warmup':
        # Readout-only adaptation: original body computation stays exactly frozen.
        import types
        import torch.nn.functional as F
        for p in model.parameters():p.requires_grad_(p is embedding)
        module=model.get_input_embeddings()
        def frozen_input(module,ids):return F.embedding(ids,module.weight.detach(),module.padding_idx)
        module.forward=types.MethodType(frozen_input,module)
    rowmask=torch.zeros(embedding.shape[0],dtype=torch.bool,device='cuda');rowmask[ACTION_IDS]=True
    protected=embedding.detach()[~rowmask].clone()
    original_backbone={n:p.detach().clone()for n,p in model.named_parameters()if p is not embedding}if a.arm=='warmup'else None
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embedding],'factor':1.,'weight_decay':policy['weight_decay']},
                                {'params':[embedding],'factor':1. if a.arm=='warmup'else policy['action_embedding_lr_factor'],'weight_decay':0.}],lr=policy['lr'])
    state_path=out/'optimizer.pt'
    if a.stage>1:optimizer.load_state_dict(torch.load(state_path,map_location='cuda',weights_only=True))
    reference=None
    if a.arm=='preference':
        reference=AutoModelForCausalLM.from_pretrained(ROOT/'warmup/last',local_files_only=True).to('cuda');attach(reference,'q4')
        reference.requires_grad_(False).eval()
    course=Course(tokenizer,a.stage);head=torch.tensor(body_ids(tokenizer),device='cuda');losses=[];components=[]
    steps=policy['format_warmup_steps']if a.arm=='warmup'else policy['steps_per_stage']
    started=time.monotonic();base_lr=policy['warmup_lr']if a.arm=='warmup'else policy['lr']
    for step in range(1,steps+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        progress=step/steps if a.arm=='warmup'else((a.stage-1)*steps+step)/(policy['stages']*steps)
        rate=base_lr*min(1.,step/40)*(.4+.6*(1+math.cos(math.pi*progress))/2)
        for g in optimizer.param_groups:g['lr']=rate*g['factor']
        batch=course.batch(step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):loss,parts=separate_loss(model,batch,head)
        if not torch.isfinite(loss):raise ValueError('Nonfinite SFT loss')
        loss.backward();total=float(loss.detach());del loss,batch
        if reference is not None:
            pref=course.preferences(policy['dpo_rows'],'cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):dpo=preference_loss(model,reference,*pref,policy['dpo_beta'])
            if not torch.isfinite(dpo):raise ValueError('Nonfinite DPO loss')
            (policy['dpo_weight']*dpo).backward();parts['dpo']=float(dpo.detach());total+=policy['dpo_weight']*parts['dpo']
            del pref,dpo
        embedding.grad.mul_(rowmask[:,None]);torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        losses.append(total);components.append(parts)
        if step==1 or step%25==0:
            record={'phase':'training','arm':a.arm,'stage':a.stage,'step':step,'steps':steps,
                    'loss':sum(losses[-25:])/len(losses[-25:]),'components':parts,'seconds':time.monotonic()-started}
            write(out/'status.json',record)
            if step%100==0:print(json.dumps(record),flush=True)
    assert torch.equal(protected,embedding.detach()[~rowmask])
    if original_backbone is not None:
        assert all(torch.equal(p.detach(),original_backbone[n])for n,p in model.named_parameters()if p is not embedding)
    save(model,tokenizer,out/'last','q4');torch.save(optimizer.state_dict(),state_path)
    replica,metadata=packed_copy(model,out/f'stage-{a.stage}.mkqb','q4');replica.to('cuda').eval();compact_head(replica,output_ids(tokenizer))
    torch.backends.cuda.matmul.allow_tf32=False
    metrics=development(replica,tokenizer);key=selection(metrics)
    write(out/f'development-stage-{a.stage}.json',metrics)
    previous=json.loads((out/'best.json').read_text())if(out/'best.json').exists()else None
    if previous is None or key>previous['key']:
        save(model,tokenizer,out/'best','q4');write(out/'best.json',{'stage':a.stage,'key':key,'master_sha256':sha(out/'best/model.safetensors')})
    record={'arm':a.arm,'stage':a.stage,'steps':steps,'sample_plan_digest':course.digest,'counts':dict(course.counts),
            'protected_original_input_rows_unchanged':True,'protected_rows_sha256':hashlib.sha256(protected.cpu().numpy().tobytes()).hexdigest(),
            'key':key,'summary':brief(metrics),'training_seconds':time.monotonic()-started,'loss_last25':sum(losses[-25:])/25,
            'Q4_from_first_update':True,'body_loss_weight':.5,'action_loss_separate':True,'packet':metadata,
            'action_preferences_only':a.arm=='preference','frozen_reference':'warmup/last'if reference is not None else None}
    record['backbone_bit_identical_after_head_only_warmup']=a.arm=='warmup'
    write(result_path,record);write(out/'status.json',{'phase':'complete_stage','stage':a.stage,'steps':steps,'key':key})
    print(json.dumps({'arm':a.arm,'stage':a.stage,'key':key,'summary':record['summary']}),flush=True)


if __name__=='__main__':main()
