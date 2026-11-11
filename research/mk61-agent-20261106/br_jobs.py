"""Fixed-budget full-Q4 fitting, selection on training only, then held-out audits."""
import argparse
import math
import time
import torch
from br_common import ROOT,ARMS,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from br_model import Full,load
from br_course import Course,loss
from br_eval import evaluate,states,selection,brief
from native_export import packet
from bl_spec import install
from bk_independent_generate import generate


def status(folder,phase,**extra):write(folder/'status.json',{'phase':phase,'unix':time.time(),**extra})


def train(arm):
    check_frozen();policy=read(ROOT/'policy.json');out=ROOT/arm;out.mkdir(exist_ok=True)
    assert not(out/'training.json').exists(),'No accidental repeat SGD'
    torch.manual_seed(policy['model_seed']);model=Full(arm);model.train()
    model.save_checkpoint(out/'start.safetensors');replica,_=model.packed(out/'start.mkqb')
    assert packet(out/'start.mkqb')[1]==packet(ROOT/'initial'/arm/'model.mkqb')[1]
    replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
    probes=[]
    for p in read(ROOT/'initial-probes.json')[:6]:
        v=generate(replica,model.tokenizer,[p['prompt']],p['forced_action'])[0]
        probes.append({'prompt':p['prompt'],'forced_action':p['forced_action'],'generation':v})
    write(out/'initial-receipt.json',{'B200_initial_Q4_exact':True,'optimizer_updates':0,'probes':probes})
    head=torch.tensor(body_ids(model.tokenizer),device='cuda');course=Course(model.tokenizer)
    groups=[]
    for embedding in [False,True]:
        for decay in [False,True]:
            values=[p for n,p in model.named_parameters()if p.requires_grad and('.embed_tokens.'in n)==embedding and(p.ndim>1)==decay]
            if values:groups.append({'params':values,'base_lr':policy['lr_embeddings'if embedding else'lr'],
                                     'weight_decay':policy['weight_decay']if decay else 0.})
    assert sum(p.numel()for g in groups for p in g['params'])==read(ROOT/'initialization.json')['parameter_counts'][arm]
    optimizer=torch.optim.AdamW(groups);best=None;started=time.monotonic();losses=[]
    def measured(step,replica):
        nonlocal best
        status(out,'training_fit_audit',step=step)
        state=states(replica,model.tokenizer);report=evaluate(replica,model.tokenizer,'train')
        score,checks=selection(report,state)
        write(out/f'states-{step}.json',state);write(out/f'train-{step}.json',report)
        write(out/f'selection-{step}.json',{'key':score,'checks':checks,'held_out_seen':False})
        if best is None or score>best['key']:
            model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':score,'checks':checks,'sha256':sha(out/'best.safetensors')}
            write(out/'best.json',best)
        print({'arm':arm,'step':step,'checks':checks,'results':brief(report)},flush=True)
    measured(0,replica);del replica;torch.cuda.empty_cache()
    for step in range(1,policy['steps']+1):
        factor=min(1.,step/policy['warmup'])*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for g in optimizer.param_groups:g['lr']=g['base_lr']*factor
        optimizer.zero_grad(set_to_none=True)
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,course.batch(step,'cuda'),head)
        assert torch.isfinite(value);value.backward()
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:status(out,'training',step=step,steps=policy['steps'],loss=sum(losses[-50:])/len(losses[-50:]),parts=parts,seconds=time.monotonic()-started)
        if step in policy['checkpoints']:
            model.save_checkpoint(out/f'step-{step}.safetensors');replica,_=model.packed(out/f'step-{step}.mkqb')
            replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer));measured(step,replica)
            del replica;torch.cuda.empty_cache();check_frozen()
    model.save_checkpoint(out/'last.safetensors')
    write(out/'training.json',{'steps':policy['steps'],'optimizer_updates':policy['steps'],'trainable_parameters':model.trainable_count(),
        'counts':dict(course.counts),'draw_digest':course.digest,'Q4_every_forward':True,'seconds':time.monotonic()-started,
        'training_only_selection':True,'all_old_and_added_parameters_trainable':True,'seed':policy['model_seed']})
    status(out,'trained',step=policy['steps']);check_frozen()


def audit(arm):
    check_frozen();chosen=read(ROOT/'preselected.json')['branches'][arm];out=ROOT/arm
    checkpoints=[('selected',chosen['step'],'best.safetensors')]
    if chosen['step']!=read(ROOT/'policy.json')['steps']:checkpoints.append(('final',read(ROOT/'policy.json')['steps'],'last.safetensors'))
    results={}
    for label,step,filename in checkpoints:
        folder=ROOT/'export'/arm/label;folder.mkdir(parents=True,exist_ok=True)
        a=Full(arm,checkpoint=out/filename);model,_=a.packed(folder/'model.mkqb')
        a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);a.tokenizer.save_pretrained(folder/'hf')
        tok=a.tokenizer;count=a.trainable_count();del a
        model.cuda().eval();compact_head(model,output_ids(tok));panels={}
        for panel in ['wording','inputs','new_ast']:
            status(out,'held_out_audit',checkpoint=label,step=step,panel=panel)
            r=evaluate(model,tok,panel);write(out/(label+'-'+panel+'.json'),r);panels[panel]=brief(r)
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':count,
              'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
              'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},
              'step':step,'selection_used_held_out':False,'research_only':True,'main_profile_replacement':False})
        results[label]={'step':step,'panels':panels};del model;torch.cuda.empty_cache()
    write(out/'held-out-summary.json',results);status(out,'complete');check_frozen()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['train','audit']);p.add_argument('--arm',choices=ARMS,required=True);args=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;install()
    (train if args.action=='train'else audit)(args.arm)
