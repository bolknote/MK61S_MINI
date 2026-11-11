"""Train translator adapters only, freeze choice, and finish whole-agent audits."""
import math
import shutil
import time
import torch
from bu_common import ROOT,SOURCE,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from bu_model import Translator,actor,frozen_digest
from bu_course import Course,loss
from bu_eval import evaluate,key,brief
from bs_resources import configure,headroom,duty
from native_export import packet


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert not(ROOT/'training.json').exists()and not(ROOT/'preselected.json').exists()
    frozen,tok=actor('cuda:0');compact_head(frozen,output_ids(tok));actor_before=frozen_digest(frozen)
    status('parent_development');baseline=evaluate(frozen,frozen,tok,'development',policy,status);write(ROOT/'parent-development.json',baseline)
    print({'parent_development':brief(baseline)},flush=True)
    model=Translator('cuda:0',ROOT/'initial.safetensors');before=frozen_digest(model);assert before==read(ROOT/'prepared.json')['frozen_translator_digest']
    assert model.trainable_count()==317440;torch.manual_seed(policy['model_seed'])
    optimizer=torch.optim.AdamW([p for p in model.parameters()if p.requires_grad],lr=policy['lr'],weight_decay=policy['weight_decay'])
    head=torch.tensor(body_ids(tok),device='cuda:0');course=Course(tok);started=time.monotonic();losses=[];torch.cuda.reset_peak_memory_stats()
    best={'step':0,'key':[True,0,0,0,0,0,0],'fallback':'original translator'};write(ROOT/'best.json',best)
    for step in range(1,policy['steps']+1):
        if step==1 or step%100==0:headroom(policy,status)
        active=time.monotonic();factor=min(1.,step/75)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=policy['lr']*factor
        optimizer.zero_grad(set_to_none=True);total=0.
        for batch in course.step(step,'cuda:0'):
            with torch.nn.utils.parametrize.cached():value=loss(model,batch,head)
            assert torch.isfinite(value);(value/4).backward();total+=float(value.detach())/4
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();torch.cuda.synchronize();duty(active,policy);losses.append(total)
        if step==1 or step%50==0:status('training',step=step,steps=policy['steps'],loss=sum(losses[-50:])/len(losses[-50:]),
            peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,seconds=time.monotonic()-started)
        if step in policy['checkpoints']:
            model.save_checkpoint(ROOT/f'step-{step}.safetensors');packed,_=model.packed(ROOT/f'step-{step}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(tok))
            assert frozen_digest(model)==before and frozen_digest(frozen)==actor_before
            status('development',step=step);report=evaluate(frozen,packed,tok,'development',policy,status);score,checks=key(report,baseline)
            write(ROOT/f'development-{step}.json',report);write(ROOT/f'selection-{step}.json',{'key':score,'checks':checks,'closed_seen':False})
            if score[0]and(best['step']==0 or score>best['key']):
                model.save_checkpoint(ROOT/'best.safetensors');best={'step':step,'key':score,'checks':checks,'sha256':sha(ROOT/'best.safetensors')};write(ROOT/'best.json',best)
            print({'step':step,'checks':checks,'development':brief(report)},flush=True);del packed;torch.cuda.empty_cache();check_frozen()
    model.save_checkpoint(ROOT/'last.safetensors')
    assert course.digest==read(ROOT/'prepared.json')['expected_draw_digest']
    assert frozen_digest(model)==before and frozen_digest(frozen)==actor_before
    write(ROOT/'training.json',{'optimizer_updates':policy['steps'],'trainable_parameters':317440,'counts':dict(course.counts),'draw_digest':course.digest,
        'frozen_translator_tensors_unchanged':True,'actor_parameters_unchanged':True,'actor_digest':actor_before,'frozen_translator_digest':before,
        'seconds':time.monotonic()-started,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20})
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'unix':time.time()})
    del model;torch.cuda.empty_cache();roles=['baseline','final'];aliases={}
    if best['step']==0:aliases['selected']='baseline'
    elif best['step']==policy['steps']:aliases['selected']='final'
    else:roles.append('selected')
    for role in roles:
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if role=='baseline':
            shutil.copytree(SOURCE/'hf',folder/'hf',dirs_exist_ok=True);shutil.copyfile(SOURCE/'model.mkqb',folder/'model.mkqb');translator=frozen;step=0
        else:
            checkpoint=ROOT/('last.safetensors'if role=='final'else'best.safetensors');a=Translator('cuda:0',checkpoint)
            translator,_=a.packed(folder/'model.mkqb');a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf');translator.cuda().eval();del a
            compact_head(translator,output_ids(tok));step=policy['steps']if role=='final'else best['step']
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,
            'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,'step':step,
            'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'actor_source_sha256':sha(SOURCE/'model.mkqb'),
            'translator_phase_only':True,'main_profile_replacement':False})
        status('closed',role=role,step=step);r=evaluate(frozen,translator,tok,'closed',policy,status);write(ROOT/('closed-'+role+'.json'),r)
        print({'closed':role,'summary':brief(r)},flush=True)
        if role!='baseline':del translator;torch.cuda.empty_cache()
        assert frozen_digest(frozen)==actor_before;check_frozen()
    for role,source in aliases.items():shutil.copyfile(ROOT/('closed-'+source+'.json'),ROOT/('closed-'+role+'.json'))
    write(ROOT/'audit-roles.json',{'evaluated':roles,'aliases':aliases});write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,
         'optimizer_updates':policy['steps'],'selected_step':best['step'],'actor_unchanged':True,'closed_used_for_selection':False,'unix':time.time()});status('complete')


if __name__=='__main__':main()
