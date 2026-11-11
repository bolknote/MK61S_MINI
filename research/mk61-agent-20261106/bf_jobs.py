"""Two fixed matched continuations and one sealed final evaluation per treatment."""
import argparse
import json
import math
import shutil
import time
import torch
from transformers import AutoModelForCausalLM
from bf_common import ROOT,SOURCES,ARMS,read,write,sha,check_frozen,body_ids,output_ids,compact_head,ACTIONS,ACTION_IDS,CORRECT_IDS
from bf_model import agent,parent as load_parent
from bf_spec import install
from bf_course import Course,loss
from bf_eval import evaluate,key,brief
from native_export import packet
from aq_protocol import header_ids

def status(path,phase,**extra):write(path,{'phase':phase,'unix':time.time(),**extra})

def baseline(arm):
    check_frozen();model,tokenizer=load_parent(arm);compact_head(model,output_ids(tokenizer))
    report=evaluate(model,tokenizer,'development');write(ROOT/f'parent-{arm}-development.json',report)
    write(ROOT/f'baseline-{arm}-receipt.json',{'sha256':sha(ROOT/f'parent-{arm}-development.json'),'closed_opened':False,'optimizer_updates':0})
    print(json.dumps({'parent_development':brief(report)}),flush=True)

def train(arm):
    check_frozen();policy=read(ROOT/'policy.json');out=ROOT/arm;out.mkdir(exist_ok=True)
    parent=read(ROOT/f'parent-{arm}-development.json');assert sha(ROOT/f'parent-{arm}-development.json')==read(ROOT/f'baseline-{arm}-receipt.json')['sha256']
    model=agent(arm);torch.manual_seed(policy['model_seed']);model.train();original_input=model.input_digest()if arm=='lora'else None
    model.save_checkpoint(out/'start.safetensors')
    replica,_=model.packed(out/'start.mkqb');del replica
    assert packet(out/'start.mkqb')[1]==packet(SOURCE/'model.mkqb')[1],arm+' initial Q4 differs'
    master=model.merged_master();reference=AutoModelForCausalLM.from_pretrained(SOURCE/'hf',local_files_only=True).float()
    assert all(torch.equal(p,dict(reference.named_parameters())[n])for n,p in master.named_parameters()),arm+' master differs'
    del master,reference
    write(out/'initial-receipt.json',{'B200_initial_Q4_exact':True,'B200_initial_master_exact':True,
        'source_Q4_sha256':sha(SOURCE/'model.mkqb'),'trainable_parameters':model.trainable_count(),'optimizer_updates':0})
    course=Course(model.tokenizer);head=torch.tensor(body_ids(model.tokenizer),device='cuda')
    if arm=='lora':
        groups=[{'params':[p for n,p in model.named_parameters()if p.requires_grad and n!='action_head'],'base_lr':policy['lr_lora'],'weight_decay':policy['weight_decay']},
            {'params':[model.action_head],'base_lr':policy['lr_lora_actions'],'weight_decay':0.}]
    else:
        params=list(model.named_parameters());groups=[]
        for embedding in [False,True]:
            for decay in [False,True]:
                values=[p for n,p in params if('.embed_tokens.'in n)==embedding and(p.ndim>1)==decay]
                if values:groups.append({'params':values,'base_lr':policy['lr_full_embeddings']if embedding else policy['lr_full'],
                    'weight_decay':policy['weight_decay']if decay else 0.})
        assert sum(p.numel()for g in groups for p in g['params'])==3022080
    optimizer=torch.optim.AdamW(groups);model.save_checkpoint(out/'best.safetensors')
    best={'step':0,'key':key(parent,parent),'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
    losses=[];started=time.monotonic()
    for step in range(1,policy['steps']+1):
        factor=min(1.,step/100)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
        optimizer.zero_grad(set_to_none=True)
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,course.batch(step,'cuda'),head)
        assert torch.isfinite(value);value.backward();assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:status(out/'status.json','training',step=step,steps=policy['steps'],
            loss=sum(losses[-50:])/len(losses[-50:]),parts=parts,seconds=time.monotonic()-started)
        if step in policy['checkpoints']:
            if arm=='lora':assert model.input_digest()==original_input
            model.save_checkpoint(out/f'step-{step}.safetensors');replica,_=model.packed(out/f'step-{step}.mkqb')
            replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
            result=evaluate(replica,model.tokenizer,'development');score=key(result,parent);write(out/f'development-{step}.json',result)
            if score>best['key']:
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':score,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache()
            print(json.dumps({'arm':arm,'step':step,'key':score,'development':brief(result)}),flush=True)
    model.save_checkpoint(out/'last.safetensors')
    assert course.counts['run_0']==course.counts['run_1']==policy['steps']//2
    write(out/'training.json',{'steps':policy['steps'],'optimizer_updates':policy['steps'],'trainable_parameters':model.trainable_count(),
        'counts':dict(course.counts),'draw_digest':course.digest,'Q4_every_forward':True,'initial_Q4_exact':True,'initial_master_exact':True,
        'Russian_dictionary_token_ids_unchanged':True,'input_embedding_weights_frozen':arm=='lora','seconds':time.monotonic()-started})
    status(out/'status.json','trained',step=policy['steps']);check_frozen()

def audit(arm):
    check_frozen();selection=read(ROOT/'preselected.json');out=ROOT/arm;out.mkdir(exist_ok=True)
    folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
    if arm.startswith('parent_'):
        model,tokenizer=load_parent(arm.split('_',1)[1]);shutil.copytree(SOURCE/'hf',folder/'hf',dirs_exist_ok=True)
        for n in ['model.mkqb','manifest.json','protocol.json']:shutil.copyfile(SOURCE/n,folder/n)
    else:
        chosen=selection['branches'][arm];a=agent(arm,checkpoint=ROOT/arm/'best.safetensors');tokenizer=a.tokenizer
        assert sha(ROOT/arm/'best.safetensors')==chosen['sha256'];model,_=a.packed(folder/'model.mkqb')
        a.merged_master().save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf')
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','training_arm':arm,'quantization_mode':'q4','parameter_count':3022080,
            'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
            'selected_step':chosen['step'],'selected_checkpoint_sha256':chosen['sha256'],'selection_used_closed_test':False,
            'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},
            'input_embedding_weights_frozen':arm=='lora'})
        write(folder/'protocol.json',{'kind':'spec-natural-v1','arm':'spec','context':1024,'codec':'ay_codec.py',
            'actions':ACTIONS,'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,
            'neural_headers':{x:header_ids(tokenizer,x)for x in ['write','run','diag']}})
    model.cuda().eval();compact_head(model,output_ids(tokenizer));result=evaluate(model,tokenizer,'closed')
    write(out/'closed.json',result);write(folder/'output-token-ids.json',output_ids(tokenizer));status(out/'status.json','complete');check_frozen()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['baseline','train','audit']);p.add_argument('--arm',choices=['parent_lora','parent_full',*ARMS]);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    install();SOURCE=SOURCES[a.arm.split('_',1)[-1]]
    if a.action=='baseline':baseline(a.arm)
    elif a.action=='train':train(a.arm)
    else:audit(a.arm)
