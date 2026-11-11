"""Shared-GPU, bounded-memory Q4 continuation, with protected development choice."""
import argparse
import math
import shutil
import time
import torch
from bs_common import ROOT,SOURCE,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from bs_model import agent,parent
from bs_course import Course,loss
from bs_eval import evaluate,key,brief
from bs_resources import configure,headroom,duty
from native_export import packet


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def protected(report,parent_compact,parent_long):
    score,checks=key(report,parent_compact);a=report['own']['summary'];b=parent_long['own']['summary']
    checks.update(working_completion=a['passed']>=b['passed'],working_repairs=a['wrong_starts_repaired']>=b['wrong_starts_repaired'],
                  working_false_DONE=a['false_DONE']<=b['false_DONE'],working_correct_starts=a['correct_starts_completed']>=b['correct_starts_completed'])
    score[0]=bool(score[0]and all(checks[k]for k in ['working_completion','working_repairs','working_false_DONE','working_correct_starts']))
    return score,checks


def baseline(policy):
    model,tokenizer=parent('cuda:0');compact_head(model,output_ids(tokenizer))
    for profile in ['compact','long']:
        status('parent_development',profile=profile)
        report=evaluate(model,tokenizer,'development',profile,policy);write(ROOT/('parent-development-'+profile+'.json'),report)
        print({'profile':profile,'parent':brief(report)},flush=True)
    del model;torch.cuda.empty_cache()


def train(policy):
    assert not(ROOT/'training.json').exists(),'No duplicate SGD'
    parent_compact=read(ROOT/'parent-development-compact.json');parent_long=read(ROOT/'parent-development-long.json')
    torch.manual_seed(policy['model_seed']);model=agent('cuda:0');model.train();model.save_checkpoint(ROOT/'start.safetensors')
    replica,_=model.packed(ROOT/'start.mkqb');assert packet(ROOT/'start.mkqb')[1]==packet(SOURCE/'model.mkqb')[1];del replica
    write(ROOT/'initial-receipt.json',{'Q4_payload_equals_working_parent':True,'optimizer_updates':0,'parent_Q4_sha256':sha(SOURCE/'model.mkqb')})
    head=torch.tensor(body_ids(model.tokenizer),device='cuda:0');course=Course(model.tokenizer);groups=[]
    for embed in [False,True]:
        for decay in [False,True]:
            params=[p for n,p in model.named_parameters()if p.requires_grad and('.embed_tokens.'in n)==embed and(p.ndim>1)==decay]
            if params:groups.append({'params':params,'base_lr':policy['lr_embeddings'if embed else'lr'],'weight_decay':policy['weight_decay']if decay else 0.})
    assert sum(p.numel()for g in groups for p in g['params'])==3022080
    optimizer=torch.optim.AdamW(groups);model.save_checkpoint(ROOT/'best.safetensors')
    best={'step':0,'fallback_profile':'long','key':[True,0,0,0,0,0,0,0],'sha256':sha(ROOT/'best.safetensors')}
    write(ROOT/'best.json',best);started=time.monotonic();losses=[];torch.cuda.reset_peak_memory_stats()
    for step in range(1,policy['steps']+1):
        if step==1 or step%100==0:headroom(policy,status)
        active=time.monotonic();factor=min(1.,step/100)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
        optimizer.zero_grad(set_to_none=True);total=0.;parts=[]
        for batch in course.step(step,'cuda:0'):
            with torch.nn.utils.parametrize.cached():value,p=loss(model,batch,head)
            assert torch.isfinite(value);(value/4).backward();total+=float(value.detach())/4;parts.append(p)
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();torch.cuda.synchronize();losses.append(total)
        duty(active,policy)
        if step==1 or step%50==0:status('training',step=step,steps=policy['steps'],loss=sum(losses[-50:])/len(losses[-50:]),
            peak_allocated_MiB=torch.cuda.max_memory_allocated()/2**20,peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,seconds=time.monotonic()-started)
        if step in policy['checkpoints']:
            model.save_checkpoint(ROOT/f'step-{step}.safetensors');replica,_=model.packed(ROOT/f'step-{step}.mkqb')
            replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer));status('development_audit',step=step)
            report=evaluate(replica,model.tokenizer,'development',shared_policy=policy);score,checks=protected(report,parent_compact,parent_long)
            write(ROOT/f'development-{step}.json',report);write(ROOT/f'selection-{step}.json',{'key':score,'checks':checks,'closed_seen':False})
            if score[0]and(score>best['key']or best['step']==0):
                model.save_checkpoint(ROOT/'best.safetensors');best={'step':step,'key':score,'checks':checks,'sha256':sha(ROOT/'best.safetensors')};write(ROOT/'best.json',best)
            del replica;torch.cuda.empty_cache();check_frozen();print({'step':step,'checks':checks,'results':brief(report)},flush=True)
    model.save_checkpoint(ROOT/'last.safetensors')
    write(ROOT/'training.json',{'optimizer_updates':policy['steps'],'steps':policy['steps'],'Q4_every_forward':True,'trainable_parameters':3022080,
       'effective_batch':32,'microbatch':8,'gradient_accumulation':4,'counts':dict(course.counts),'draw_digest':course.digest,
       'seconds':time.monotonic()-started,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,
       'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'GPU_duty_fraction':policy['GPU_duty_fraction'],'allocator_MiB_limit':policy['allocator_MiB']})
    assert course.digest==read(ROOT/'prepared.json')['expected_draw_digest']
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'working_parent_preservation_required':True,'unix':time.time()})


def audits(policy):
    chosen=read(ROOT/'preselected.json')['chosen'];roles=['parent_compact','parent_long','final'];aliases={}
    if chosen['step']==0:aliases['selected']='parent_long'
    elif chosen['step']==policy['steps']:aliases['selected']='final'
    else:roles.append('selected')
    for role in roles:
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if role.startswith('parent'):
            model,tok=parent('cuda:0');shutil.copytree(SOURCE/'hf',folder/'hf',dirs_exist_ok=True);shutil.copyfile(SOURCE/'model.mkqb',folder/'model.mkqb')
            step=0;profile='long'if role=='parent_long'else'compact'
        else:
            checkpoint=ROOT/('last.safetensors'if role=='final'else'best.safetensors');a=agent('cuda:0',checkpoint=checkpoint)
            model,_=a.packed(folder/'model.mkqb');a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);a.tokenizer.save_pretrained(folder/'hf')
            tok=a.tokenizer;model.cuda();del a;step=policy['steps']if role=='final'else chosen['step'];profile='compact'
        compact_head(model,output_ids(tok));model.eval();status('closed_audit',role=role,step=step,profile=profile)
        report=evaluate(model,tok,'closed',profile,policy);write(ROOT/('closed-'+role+'.json'),report)
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,
           'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,'step':step,'profile':profile,
           'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'selection_used_closed':False,'main_profile_replacement':False})
        del model;torch.cuda.empty_cache();print({'role':role,'closed':brief(report)},flush=True)
    for role,source in aliases.items():
        shutil.copyfile(ROOT/('closed-'+source+'.json'),ROOT/('closed-'+role+'.json'));shutil.copytree(ROOT/'export'/source,ROOT/'export'/role,dirs_exist_ok=True)
    write(ROOT/'audit-roles.json',{'evaluated':roles,'aliases':aliases});check_frozen()
    write(ROOT/'complete.json',{'complete':True,'optimizer_updates':policy['steps'],'all_audits_complete':True,'closed_used_for_selection':False,'unix':time.time()});status('complete')


if __name__=='__main__':
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    baseline(policy);train(policy);audits(policy)
