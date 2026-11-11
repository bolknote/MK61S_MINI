"""Repair the BU adapter; stop at the first protected checkpoint, then seal audit."""
import math
import shutil
import time
import torch
from bv_common import ROOT,SOURCE,PARENT,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from bu_model import Translator,actor,frozen_digest
from be_model import load
from bv_course import Course,loss
from bv_eval import ActorCache,evaluate,fit_key,protected,brief
from bs_resources import configure,headroom,duty


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert not(ROOT/'training.json').exists()and not(ROOT/'preselected.json').exists()
    frozen,tok=actor('cuda:0');teacher,tt=load(PARENT,'cuda:0');assert tt.get_vocab()==tok.get_vocab()
    for m in [frozen,teacher]:compact_head(m,output_ids(tok))
    actor_before=frozen_digest(frozen);teacher_before=frozen_digest(teacher);cache=ActorCache();parent_fit=read(ROOT/'parent-fit.json')
    status('parent_development');baseline=evaluate(frozen,teacher,tok,'development',policy,status,cache);write(ROOT/'parent-development.json',baseline)
    print({'parent_development':brief(baseline)},flush=True)
    model=Translator('cuda:0',ROOT/'initial.safetensors');before=frozen_digest(model);assert before==read(ROOT/'prepared.json')['frozen_translator_digest']
    torch.manual_seed(policy['model_seed']);params=[p for p in model.parameters()if p.requires_grad];assert sum(p.numel()for p in params)==317440
    optimizer=torch.optim.AdamW(params,lr=policy['lr'],weight_decay=policy['weight_decay']);head=torch.tensor(body_ids(tok),device='cuda:0');course=Course(tok)
    best={'step':0,'fallback':'BU1500 research parent; not approved working profile','fit_gate_passed':False};write(ROOT/'best.json',best)
    started=time.monotonic();losses=[];torch.cuda.reset_peak_memory_stats();actual=0
    for step in range(1,policy['max_steps']+1):
        if step==1 or step%100==0:headroom(policy,status)
        active=time.monotonic();factor=min(1.,step/25)*(.25+.75*(1+math.cos(math.pi*step/policy['max_steps']))/2)
        for group in optimizer.param_groups:group['lr']=policy['lr']*factor
        optimizer.zero_grad(set_to_none=True);total=0.;parts=[]
        for batch in course.step(step,'cuda:0'):
            with torch.nn.utils.parametrize.cached():value,p=loss(model,teacher,batch,head,policy['KD_weight'])
            assert torch.isfinite(value);(value/policy['accumulation']).backward();total+=float(value.detach())/policy['accumulation'];parts.append(p)
        torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True);optimizer.step();torch.cuda.synchronize();duty(active,policy);losses.append(total);actual=step
        if step==1 or step%50==0:status('training',step=step,max_steps=policy['max_steps'],loss=sum(losses[-50:])/len(losses[-50:]),
             peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,seconds=time.monotonic()-started)
        if step==200:assert course.digest==read(ROOT/'prepared.json')['first200_draw_digest']
        if step in policy['checkpoints']:
            model.save_checkpoint(ROOT/f'step-{step}.safetensors');packed,_=model.packed(ROOT/f'step-{step}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(tok))
            assert frozen_digest(model)==before and frozen_digest(frozen)==actor_before and frozen_digest(teacher)==teacher_before
            status('fit_regression',step=step);fit=evaluate(frozen,packed,tok,'fit',policy,status,cache);score,checks=fit_key(fit,parent_fit)
            write(ROOT/f'fit-{step}.json',fit);passed=bool(score[0]);development=None
            if passed:
                status('development',step=step);development=evaluate(frozen,packed,tok,'development',policy,status,cache)
                write(ROOT/f'development-{step}.json',development);checks.update(protected(development,baseline));passed=all(checks.values())
            write(ROOT/f'selection-{step}.json',{'fit_key':score,'checks':checks,'passed':passed,'closed_seen':False})
            print({'step':step,'fit':brief(fit),'protected':checks,'development':brief(development)if development else None},flush=True)
            if passed:
                model.save_checkpoint(ROOT/'best.safetensors');best={'step':step,'fit_gate_passed':True,'checks':checks,'sha256':sha(ROOT/'best.safetensors')};write(ROOT/'best.json',best)
            else:course.prioritize(fit,step);write(ROOT/'priority-updates.json',course.priority_updates)
            del packed;torch.cuda.empty_cache();check_frozen()
            if passed:break
    model.save_checkpoint(ROOT/'last.safetensors')
    assert frozen_digest(model)==before and frozen_digest(frozen)==actor_before and frozen_digest(teacher)==teacher_before
    write(ROOT/'training.json',{'optimizer_updates':actual,'max_planned_steps':policy['max_steps'],'stopped_at_first_safe_checkpoint':best['step']>0,
        'trainable_parameters':317440,'counts':dict(course.counts),'draw_digest':course.digest,'priority_updates':course.priority_updates,
        'actor_parameters_unchanged':True,'teacher_parameters_unchanged':True,'frozen_translator_tensors_unchanged':True,
        'actor_digest':actor_before,'teacher_digest':teacher_before,'frozen_translator_digest':before,
        'seconds':time.monotonic()-started,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20})
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'unix':time.time(),'working_profile_unchanged':True})
    del model;torch.cuda.empty_cache();roles=['original','parent','final'];aliases={'selected':'final'if best['step']>0 else'parent'}
    for role in roles:
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if role in ['original','parent']:
            source=SOURCE if role=='original'else PARENT;shutil.copytree(source/'hf',folder/'hf',dirs_exist_ok=True);shutil.copyfile(source/'model.mkqb',folder/'model.mkqb')
            translator=frozen if role=='original'else teacher;step=0
        else:
            a=Translator('cuda:0',ROOT/'last.safetensors');translator,_=a.packed(folder/'model.mkqb');a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf');translator.cuda().eval();compact_head(translator,output_ids(tok));del a;step=actual
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,'additional_updates':step,
            'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
            'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'actor_source_sha256':sha(SOURCE/'model.mkqb'),
            'translator_phase_only':True,'main_profile_replacement':False})
        status('closed',role=role,additional_updates=step);r=evaluate(frozen,translator,tok,'closed',policy,status,cache);write(ROOT/('closed-'+role+'.json'),r)
        print({'closed':role,'summary':brief(r),'actor_cache':{'hits':cache.hits,'misses':cache.misses}},flush=True)
        if role=='final':del translator;torch.cuda.empty_cache()
        assert frozen_digest(frozen)==actor_before and frozen_digest(teacher)==teacher_before;check_frozen()
    for role,source in aliases.items():shutil.copyfile(ROOT/('closed-'+source+'.json'),ROOT/('closed-'+role+'.json'))
    # Every checkpoint has a fit report; the full closed audit is mandatory after selection.
    write(ROOT/'audit-roles.json',{'evaluated':roles,'aliases':aliases});write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':actual,
         'selected_step':best['step'],'actor_unchanged':True,'closed_used_for_selection':False,'actor_cache_hits':cache.hits,'actor_cache_misses':cache.misses,'unix':time.time()});status('complete')


if __name__=='__main__':main()
