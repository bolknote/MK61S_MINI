"""Complete fixed readout-only QAT, preselect on cycles, then audit fresh Q4 tasks."""
import math
import shutil
import time
import torch
from cc_common import ROOT,ACTOR,WORKING,PARENT,read,write,sha,check_frozen,output_ids,compact_head,ACTION_IDS
from cc_model import Actor,ROWS
from cc_course import Course,loss
from cc_features import extract
from cc_eval import Cache,evaluate,select
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom

def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})

def unchanged_body(model,parent):
    reference=dict(parent.named_parameters());changed=[]
    for name,p in model.named_parameters():
        q=reference[name]
        if torch.equal(p,q):continue
        assert name=='model.embed_tokens.weight',name
        mask=torch.ones(len(p),device=p.device,dtype=torch.bool);mask[[ACTION_IDS[i]for i in ROWS]]=False
        assert torch.equal(p[mask],q[mask]);changed=[i for i in ACTION_IDS if not torch.equal(p[i],q[i])]
    return changed

def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert read(ROOT/'GPU-preflight.json')['complete']and not(ROOT/'training.json').exists()
    status('feature_extraction');features=extract(policy,status)
    # No encoder gradient is needed: the only learned operation is h @ Q4(head).
    model=Actor('cpu',ROOT/'initial.safetensors');before=frozen_digest(model);course=Course();params=[model.decision_head]
    optimizer=torch.optim.AdamW(params,lr=policy['lr'],weight_decay=policy['weight_decay']);started=time.monotonic();losses=[]
    for step in range(1,policy['max_steps']+1):
        factor=min(1.,step/policy['warmup'])*(.3+.7*(1+math.cos(math.pi*step/policy['max_steps']))/2)
        optimizer.param_groups[0]['lr']=policy['lr']*factor;optimizer.zero_grad(set_to_none=True)
        value,parts=loss(model,course.batch(step),policy);assert torch.isfinite(value);value.backward()
        torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True);optimizer.step();losses.append(float(value.detach()))
        if step==200:assert course.digest==read(ROOT/'CPU-preflight.json')['first200_draw_digest']
        if step==1 or step%50==0:status('training',step=step,max_steps=policy['max_steps'],loss=sum(losses[-50:])/len(losses[-50:]),parts=parts)
        if step in policy['checkpoints']:model.save_checkpoint(ROOT/f'step-{step}.safetensors')
    model.save_checkpoint(ROOT/'last.safetensors');assert frozen_digest(model)==before
    write(ROOT/'training.json',{'optimizer_updates':step,'trainable_parameters':384,'counts':dict(course.counts),'draw_digest':course.digest,
        'Q4_every_trainable_forward':True,'frozen_encoder_and_body_unchanged':True,'frozen_actor_digest':before,
        'features_sha256':features['sha256'],'seconds':time.monotonic()-started,'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,
        'training_device':'CPU FP32 readout, cached frozen Q4 B200 features','only_action_rows_may_change':True})
    del model;parent,tok=load(ACTOR,'cuda:0');working,t=load(WORKING,'cuda:0');translator,t=load(PARENT,'cuda:0')
    for m in [parent,working,translator]:compact_head(m,output_ids(tok))
    parent_digest=frozen_digest(parent);translator_digest=frozen_digest(translator);cache=Cache()
    def measured(current,role):
        cache.actor_role=role;reports={}
        for split in ['development','retention']:
            status('selection_cycles',role=role,split=split);reports[split]=evaluate(current,translator,tok,split,policy,status,cache)
            write(ROOT/f'{role}-{split}.json',reports[split]);print({'role':role,'split':split,'summary':reports[split]['own']['summary']},flush=True)
        return reports
    baseline=measured(parent,'parent');control=measured(working,'working');best={'step':0,'eligible':False,'fallback':'parent research checkpoint; working product unchanged'};write(ROOT/'best.json',best)
    for step in policy['checkpoints']:
        current=Actor('cpu',ROOT/f'step-{step}.safetensors');packed,_=current.packed(ROOT/f'step-{step}.mkqb');packed.cuda().eval();compact_head(packed,output_ids(tok))
        changed=unchanged_body(packed,parent);reports=measured(packed,f'step-{step}');decision=select(reports,baseline,control);decision['changed_action_token_rows']=changed
        write(ROOT/f'selection-{step}.json',decision)
        if decision['eligible']and(not best['eligible']or decision['key']>best['decision']['key']):
            shutil.copy2(ROOT/f'step-{step}.safetensors',ROOT/'best.safetensors');best={'step':step,'eligible':True,'decision':decision};write(ROOT/'best.json',best)
        del current,packed;torch.cuda.empty_cache();check_frozen()
    write(ROOT/'preselected.json',{'chosen':best,'closed_seen':False,'unix':time.time(),'product_profile_modified':False})
    roles={};aliases={}
    def export(role,source=None,checkpoint=None):
        folder=ROOT/'export'/role;folder.mkdir(parents=True,exist_ok=True)
        if source is not None:
            shutil.copytree(source,folder,dirs_exist_ok=True);packed=parent if role=='parent'else working
        else:
            current=Actor('cpu',ROOT/checkpoint);packed,_=current.packed(folder/'model.mkqb');current.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf')
            packed.cuda().eval();compact_head(packed,output_ids(tok));unchanged_body(packed,parent);del current
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,
            'packed_sha256':sha(folder/'model.mkqb'),'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},
            'readout_only':True,'research_only':True,'translator_frozen':True})
        return packed
    models=[('working',WORKING,None),('parent',ACTOR,None)]
    if best['step']:models.append(('selected',None,'best.safetensors'))
    else:aliases['selected']='parent'
    if best['step']!=policy['max_steps']:models.append(('final',None,'last.safetensors'))
    else:aliases['final']='selected'
    for role,source,checkpoint in models:
        packed=export(role,source,checkpoint);cache.actor_role=role;status('closed',role=role)
        result=evaluate(packed,translator,tok,'closed',policy,status,cache);write(ROOT/f'closed-{role}.json',result);roles[role]=['original']
        print({'closed':role,'summary':result['own']['summary']},flush=True)
        if source is None:del packed;torch.cuda.empty_cache()
        assert frozen_digest(parent)==parent_digest and frozen_digest(translator)==translator_digest;check_frozen()
    write(ROOT/'audit-roles.json',{'evaluated':roles,'aliases':aliases,'selected_step':best['step'],'actual_updates':policy['max_steps']})
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':policy['max_steps'],'selected_step':best['step'],
        'translator_unchanged':True,'parent_body_unchanged':True,'unix':time.time()});status('complete')

if __name__=='__main__':main()
