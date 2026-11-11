"""Resume only immutable checkpoint evaluation after a missing analysis dependency."""
import shutil
import time
import torch
from cd_common import ROOT,ACTOR,WORKING,PARENT,read,write,sha,check_frozen,output_ids,compact_head
from cd_model import Actor
from cd_eval import Cache,evaluate,select
from cd_jobs import status,unchanged_body
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom
from by_finish import analyze

def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    plan=read(ROOT/'recovery-frozen.json')
    for n,d in plan['unchanged_training_files'].items():assert sha(ROOT/n)==d,n
    assert read(ROOT/'training.json')['optimizer_updates']==800
    assert not(ROOT/'preselected.json').exists()and not(ROOT/'complete.json').exists()
    parent,tok=load(ACTOR,'cuda:0');working,t=load(WORKING,'cuda:0');translator,t=load(PARENT,'cuda:0')
    for m in [parent,working,translator]:compact_head(m,output_ids(tok))
    parent_digest=frozen_digest(parent);translator_digest=frozen_digest(translator);cache=Cache()
    def measured(current,role):
        cache.actor_role=role;reports={}
        for split in ['development','retention']:
            status('selection_cycles',role=role,split=split)
            reports[split]=read(ROOT/f'{role}-{split}.json')if(ROOT/f'{role}-{split}.json').exists()else evaluate(current,translator,tok,split,policy,status,cache)
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
            'review_gate_only':True,'research_only':True,'translator_frozen':True})
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
    for n,d in plan['unchanged_training_files'].items():assert sha(ROOT/n)==d,n
    write(ROOT/'recovery-complete.json',{'complete':True,'additional_optimizer_updates':0,'original_800_updates_preserved':True,'evaluation_protocol_unchanged':True})

if __name__=='__main__':main()
