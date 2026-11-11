"""Continue BU1500 with real phase pairs; select by whole-cycle behavior."""
import math
import shutil
import time
import torch
from bx_common import ROOT,ACTOR,PARENT,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from bx_course import Course,loss
from bx_eval import Cache,evaluate,selection,brief
from bu_model import Translator,frozen_digest
from be_model import load
from bs_resources import configure,headroom,duty


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    pre=read(ROOT/'GPU-preflight.json');assert pre['complete']and pre['optimizer_updates']==0 and pre['peak_reserved_MiB']<=policy['allocator_MiB']
    assert not(ROOT/'training.json').exists()and not(ROOT/'preselected.json').exists()
    actor,tok=load(ACTOR,'cuda:0');teacher,t=load(PARENT,'cuda:0');assert tok.get_vocab()==t.get_vocab()
    for m in [actor,teacher]:compact_head(m,output_ids(tok))
    before_actor=frozen_digest(actor);before_teacher=frozen_digest(teacher);cache=Cache();parent_fit=read(ROOT/'parent-fit.json')
    status('parent_development');parent=evaluate(actor,teacher,tok,'development',policy,status,cache);write(ROOT/'parent-development.json',parent)
    print({'parent_development':brief(parent)},flush=True)
    model=Translator('cuda:0',ROOT/'initial.safetensors');before=frozen_digest(model);assert before==read(ROOT/'CPU-preflight.json')['frozen_translator_digest']
    torch.manual_seed(policy['model_seed']);params=[p for p in model.parameters()if p.requires_grad];assert sum(p.numel()for p in params)==317440
    optimizer=torch.optim.AdamW(params,lr=policy['lr'],weight_decay=policy['weight_decay']);head=torch.tensor(body_ids(tok),device='cuda:0');course=Course(tok)
    best={'step':0,'fallback':'BU1500 research parent','all_checks_passed':False};write(ROOT/'best.json',best)
    losses=[];started=time.monotonic();torch.cuda.reset_peak_memory_stats();actual=0
    for step in range(1,policy['max_steps']+1):
        if step==1 or step%100==0:headroom(policy,status)
        active=time.monotonic();factor=min(1.,step/25)*(.3+.7*(1+math.cos(math.pi*step/policy['max_steps']))/2)
        for group in optimizer.param_groups:group['lr']=policy['lr']*factor
        optimizer.zero_grad(set_to_none=True);total=0.;parts=[]
        for batch in course.step(step,'cuda:0'):
            with torch.nn.utils.parametrize.cached():value,p=loss(model,teacher,batch,head,policy['JS_weight'],policy['KD_weight'])
            assert torch.isfinite(value);(value/policy['accumulation']).backward();total+=float(value.detach())/policy['accumulation'];parts.append(p)
        torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True);optimizer.step();torch.cuda.synchronize();duty(active,policy);losses.append(total);actual=step
        if step==1 or step%50==0:status('training',step=step,max_steps=policy['max_steps'],loss=sum(losses[-50:])/len(losses[-50:]),peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,seconds=time.monotonic()-started)
        if step==200:assert course.digest==read(ROOT/'CPU-preflight.json')['first200_draw_digest']
        if step not in policy['checkpoints']:continue
        model.save_checkpoint(ROOT/f'step-{step}.safetensors');packed,_=model.packed(ROOT/f'step-{step}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(tok))
        assert frozen_digest(model)==before and frozen_digest(actor)==before_actor and frozen_digest(teacher)==before_teacher
        status('fit_regression',step=step);fit=evaluate(actor,packed,tok,'fit',policy,status,cache);write(ROOT/f'fit-{step}.json',fit)
        status('development',step=step);dev=evaluate(actor,packed,tok,'development',policy,status,cache);write(ROOT/f'development-{step}.json',dev)
        decision=selection(dev,fit,parent,parent_fit);write(ROOT/f'selection-{step}.json',decision)
        print({'step':step,'fit':brief(fit),'development':brief(dev),'selection':decision},flush=True)
        if decision['passed']:
            model.save_checkpoint(ROOT/'best.safetensors');best={'step':step,'all_checks_passed':True,'decision':decision,'sha256':sha(ROOT/'best.safetensors')};write(ROOT/'best.json',best)
        course.prioritize(fit,step);write(ROOT/'priority-updates.json',course.priority_updates)
        del packed;torch.cuda.empty_cache();check_frozen()
        if decision['passed']:break
    model.save_checkpoint(ROOT/'last.safetensors')
    assert frozen_digest(model)==before and frozen_digest(actor)==before_actor and frozen_digest(teacher)==before_teacher
    write(ROOT/'training.json',{'optimizer_updates':actual,'trainable_parameters':317440,'counts':dict(course.counts),'draw_digest':course.digest,'priority_updates':course.priority_updates,
        'cumulative_regressions_initial':len(read(ROOT/'regression-history.json')['all_ids']),'cumulative_regressions_final':len(course.cumulative),
        'never_removed_regressions':True,'actor_parameters_unchanged':True,'teacher_parameters_unchanged':True,'frozen_translator_tensors_unchanged':True,
        'actor_digest':before_actor,'teacher_digest':before_teacher,'frozen_translator_digest':before,'seconds':time.monotonic()-started,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20})
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'unix':time.time(),'working_profile_unchanged':True})
    del model;torch.cuda.empty_cache()
    for role in ['parent','final']:
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if role=='parent':
            shutil.copytree(PARENT/'hf',folder/'hf',dirs_exist_ok=True);shutil.copyfile(PARENT/'model.mkqb',folder/'model.mkqb');translator=teacher
        else:
            model=Translator('cuda:0',ROOT/'last.safetensors');translator,_=model.packed(folder/'model.mkqb');model.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf');translator.cuda().eval();compact_head(translator,output_ids(tok));del model
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,'additional_updates':actual if role=='final'else 0,
            'packed_sha256':sha(folder/'model.mkqb'),'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'translator_phase_only':True})
        status('closed',role=role);r=evaluate(actor,translator,tok,'closed',policy,status,cache);write(ROOT/('closed-'+role+'.json'),r)
        print({'closed':role,'summary':brief(r)},flush=True)
        if role=='final':del translator;torch.cuda.empty_cache()
        assert frozen_digest(actor)==before_actor and frozen_digest(teacher)==before_teacher;check_frozen()
    alias='final'if best['step']else'parent';shutil.copyfile(ROOT/('closed-'+alias+'.json'),ROOT/'closed-selected.json')
    write(ROOT/'audit-roles.json',{'evaluated':['parent','final'],'aliases':{'selected':alias}})
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':actual,'selected_step':best['step'],
        'closed_used_for_selection':False,'actor_unchanged':True,'unix':time.time()});status('complete')


if __name__=='__main__':main()
