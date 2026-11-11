"""Complete a fixed actor-only QAT budget, freeze selection, audit fresh Q4 tasks."""
import math
import shutil
import time
import torch
from cb_common import ROOT,ACTOR,PARENT,read,write,sha,check_frozen,body_ids,output_ids,compact_head
from cb_model import Actor
from cb_course import Course,loss
from cb_eval import Cache,evaluate,select
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom,duty


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert read(ROOT/'GPU-preflight.json')['complete']and not(ROOT/'training.json').exists()
    parent,tok=load(ACTOR,'cuda:0');translator,t=load(PARENT,'cuda:0');assert tok.get_vocab()==t.get_vocab()
    for m in [parent,translator]:compact_head(m,output_ids(tok))
    parent_digest=frozen_digest(parent);translator_digest=frozen_digest(translator);cache=Cache();parents={}
    def measured(model,role,step=None):
        cache.actor_role=role;reports={}
        for format in ['original','full','notes']:
            reports[format]={}
            for split in ['development','retention']:
                status('selection_cycles',role=role,step=step,split=split,format=format)
                value=evaluate(model,translator,tok,split,format,policy,status,cache)
                write(ROOT/f'{role}-{split}-{format}.json',value);reports[format][split]=value
                print({'role':role,'split':split,'format':format,'summary':value['own']['summary']},flush=True)
        return reports
    parents=measured(parent,'parent',0)
    model=Actor('cuda:0',ROOT/'initial.safetensors');model.train();before=frozen_digest(model)
    assert before==read(ROOT/'CPU-preflight.json')['frozen_actor_digest'];params=[p for p in model.parameters()if p.requires_grad]
    optimizer=torch.optim.AdamW(params,lr=policy['lr'],weight_decay=policy['weight_decay']);course=Course(tok);head=torch.tensor(body_ids(tok),device='cuda:0')
    best={'step':0,'eligible':False,'fallback':'immutable parent actor'};write(ROOT/'best.json',best);losses=[];started=time.monotonic();actual=0
    torch.cuda.reset_peak_memory_stats()
    for step in range(1,policy['max_steps']+1):
        if step==1 or step%100==0:headroom(policy,status)
        active=time.monotonic();factor=min(1.,step/policy['warmup'])*(.3+.7*(1+math.cos(math.pi*step/policy['max_steps']))/2)
        for group in optimizer.param_groups:group['lr']=policy['lr']*factor
        optimizer.zero_grad(set_to_none=True);total=0.;parts=None
        for batch in course.step(step,'cuda:0'):
            with torch.nn.utils.parametrize.cached():value,parts=loss(model,parent,batch,head,policy['JS_weight'],policy['KD_weight'])
            assert torch.isfinite(value);(value/policy['accumulation']).backward();total+=float(value.detach())/policy['accumulation']
        torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True);optimizer.step();actual=step;torch.cuda.synchronize();duty(active,policy);losses.append(total)
        if step==1 or step%50==0:status('training',step=step,max_steps=policy['max_steps'],loss=sum(losses[-50:])/len(losses[-50:]),parts=parts,
            seconds=time.monotonic()-started,peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20)
        if step==200:assert course.digest==read(ROOT/'CPU-preflight.json')['first200_draw_digest']
        if step not in policy['checkpoints']:continue
        model.save_checkpoint(ROOT/f'step-{step}.safetensors');packed,_=model.packed(ROOT/f'step-{step}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(tok))
        reports=measured(packed,f'step-{step}',step);decision=select(reports,parents);write(ROOT/f'selection-{step}.json',decision)
        if decision['eligible']and(not best['eligible']or decision['key']>best['decision']['key']):
            model.save_checkpoint(ROOT/'best.safetensors');best={'step':step,'eligible':True,'decision':decision,'sha256':sha(ROOT/'best.safetensors')};write(ROOT/'best.json',best)
        assert frozen_digest(model)==before and frozen_digest(parent)==parent_digest and frozen_digest(translator)==translator_digest;check_frozen()
        print({'step':step,'selection':decision,'best':best['step']},flush=True);del packed;torch.cuda.empty_cache()
    model.save_checkpoint(ROOT/'last.safetensors')
    write(ROOT/'training.json',{'optimizer_updates':actual,'trainable_parameters':sum(p.numel()for p in params),'counts':dict(course.counts),
        'draw_digest':course.digest,'Q4_every_forward':True,'frozen_actor_digest':before,'parent_actor_digest':parent_digest,'translator_digest':translator_digest,
        'all_frozen_tensors_unchanged':frozen_digest(model)==before,'translator_unchanged':frozen_digest(translator)==translator_digest,
        'seconds':time.monotonic()-started,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20})
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'unix':time.time(),'product_profile_modified':False})
    del model;torch.cuda.empty_cache();roles={};aliases={}
    def export(role,checkpoint=None):
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if checkpoint is None:
            shutil.copytree(ACTOR,folder,dirs_exist_ok=True);packed=parent
        else:
            current=Actor('cuda:0',ROOT/checkpoint);packed,_=current.packed(folder/'model.mkqb');current.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf');packed.cuda().eval();compact_head(packed,output_ids(tok));del current
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,
            'packed_sha256':sha(folder/'model.mkqb'),'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},
            'actor_only':True,'research_only':True,'translator_frozen':True})
        return packed
    models=[('parent',None,['original','full','notes'])]
    if best['step']:models.append(('selected','best.safetensors',['full','notes']))
    else:aliases['selected']='parent'
    if best['step']!=actual:models.append(('final','last.safetensors',['notes']))
    else:aliases['final']='selected'
    for role,checkpoint,formats in models:
        packed=export(role,checkpoint);cache.actor_role=role;roles[role]=formats
        for format in formats:
            status('closed',role=role,format=format)
            value=evaluate(packed,translator,tok,'closed',format,policy,status,cache);write(ROOT/f'closed-{role}-{format}.json',value)
            print({'closed':role,'format':format,'summary':value['own']['summary']},flush=True)
        if role!='parent':del packed;torch.cuda.empty_cache()
        assert frozen_digest(parent)==parent_digest and frozen_digest(translator)==translator_digest;check_frozen()
    write(ROOT/'audit-roles.json',{'evaluated':roles,'aliases':aliases,'selected_step':best['step'],'actual_updates':actual})
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':actual,'selected_step':best['step'],
        'parent_actor_digest':parent_digest,'translator_digest':translator_digest,'translator_unchanged':True,'unix':time.time()});status('complete')


if __name__=='__main__':main()
