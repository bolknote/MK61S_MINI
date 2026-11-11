"""Dedicated balanced diagnosis training; every scored weight is actual Q4."""
import argparse
import collections
import hashlib
import json
import math
import random
import shutil
import time
import torch
import torch.nn.functional as F
from ao_common import ROOT,PARENT,HERE,INITIAL,INITIAL_PACKET,ARMS,SPLITS,CLASSES,DIAG_IDS,read,write,sha
from ao_model import Agent,load
from ao_eval import rows,features,evaluate,key,brief
from ac_protocol import prompt_ids
from native_quant import attach,export
from native_export import packet


def cache_source(model,tokenizer,split):return features(model,tokenizer,rows(split))


def prepare():
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==frozen['source_master_sha256']and sha(INITIAL_PACKET)==frozen['source_packet_sha256']
    protected=json.loads((PARENT/'prepared.json').read_text())['source_hashes']
    for n,d in protected.items():assert sha(HERE/n)==d,n
    train=rows('train');labels=torch.tensor([r['label']for r in train]);assert collections.Counter(labels.tolist())=={0:1200,1:1200,2:1200,3:1200}
    counts={};model,tokenizer=load()
    for split in ['train','development','novel-development']:
        values=rows(split)
        assert all(len(prompt_ids(tokenizer,r['prompt']))<1024 and not set(prompt_ids(tokenizer,r['prompt']))&set(DIAG_IDS)for r in values)
    cache={s:cache_source(model,tokenizer,s)for s in ['train','development','novel-development']};cache['labels']=labels
    torch.save(cache,ROOT/'source-features.pt');del model;torch.cuda.empty_cache()
    for arm in ARMS:
        model=Agent(arm,'cpu');replica,_=model.packed(ROOT/f'preflight-{arm}.mkqb');assert packet(ROOT/f'preflight-{arm}.mkqb')[1]==packet(INITIAL_PACKET)[1]
        counts[arm]=model.trainable_count();del model,replica
    probe=Agent('adapt');r=train[:4];enc=[prompt_ids(tokenizer,x['prompt'])for x in r];width=max(map(len,enc));ids=torch.zeros((4,width),device='cuda',dtype=torch.long);mask=torch.zeros_like(ids)
    for i,p in enumerate(enc):ids[i,:len(p)]=torch.tensor(p,device='cuda');mask[i,:len(p)]=1
    h=probe.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state[torch.arange(4,device='cuda'),mask.sum(1)-1]
    value=F.cross_entropy(F.linear(h,probe.head()),labels[:4].cuda());value.backward()
    assert all(torch.isfinite(p.grad).all()for p in probe.parameters()if p.grad is not None)
    assert any(p.grad is not None and bool(p.grad.abs().sum())for n,p in probe.named_parameters()if n.endswith('.0.B'))
    names=sorted(set(protected)|{p.name for p in HERE.glob('ao_*.py')if p.name not in ['ao_remote.py','ao_collect.py','ao_verify.py','ao_report.py','ao_native.py','ao_chat.py']})
    folder=ROOT/'training-source';folder.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,folder/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in folder.iterdir()},
        'source_feature_sha256':sha(ROOT/'source-features.pt'),'source_Q4_payload_exact':True,'finite_internal_gradients':True,
        'trainable_parameters':counts,'preflight_optimizer_updates':0,'private_diagnostic_rows_never_inputs':True})
    print(json.dumps({'preflight':'passed','trainable':counts,'cached_rows':{s:len(cache[s])for s in ['train','development','novel-development']}}),flush=True)


def train(arm):
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    assert sha(ROOT/'source-features.pt')==prepared['source_feature_sha256']
    cache=torch.load(ROOT/'source-features.pt',map_location='cpu',weights_only=True);values=rows('train');groups=read(ROOT/'train.jsonl')
    group_indexes={g['id']:[i for i,r in enumerate(values)if r['group_id']==g['id']]for g in groups}
    assert all(len(x)==4 for x in group_indexes.values());simple=[g['id']for g in groups if g['family']in ['unary','binary']];all_groups=list(group_indexes)
    out=ROOT/arm;out.mkdir(exist_ok=True);model=Agent(arm);original=model.input_digest();rng=random.Random(161501);digest='00'*32
    labels=cache['labels'].cuda();fixed=cache['train'].cuda()if arm=='head'else None
    optimizer=torch.optim.AdamW([{'params':[model.diagnosis_head],'lr_base':policy['head_lr'],'weight_decay':0.},
        *([{'params':[p for n,p in model.named_parameters()if p.requires_grad and n!='diagnosis_head'],'lr_base':policy['adapter_lr'],'weight_decay':.01}]if arm=='adapt'else[])])
    best=None;started=time.monotonic();losses=[]
    for step in range(1,policy['steps']+1):
        chosen=rng.choices(simple if step<=policy['curriculum_simple_steps']else all_groups,k=policy['batch_groups']);indexes=[]
        for gid in chosen:
            members=group_indexes[gid][:];rng.shuffle(members);indexes+=members
        digest=hashlib.sha256(bytes.fromhex(digest)+json.dumps(indexes,separators=(',',':')).encode()).hexdigest();indices=torch.tensor(indexes,device='cuda');target=labels[indices]
        optimizer.zero_grad(set_to_none=True);factor=min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for p in optimizer.param_groups:p['lr']=p['lr_base']*factor
        with torch.nn.utils.parametrize.cached():
            if arm=='head':h=fixed[indices]
            else:
                enc=[prompt_ids(model.tokenizer,values[i]['prompt'])for i in indexes];width=max(map(len,enc));ids=torch.zeros((len(enc),width),device='cuda',dtype=torch.long);mask=torch.zeros_like(ids)
                for i,p in enumerate(enc):ids[i,:len(p)]=torch.tensor(p,device='cuda');mask[i,:len(p)]=1
                hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state;h=hidden[torch.arange(len(ids),device='cuda'),mask.sum(1)-1]
            logits=F.linear(h,model.head()).float();ce=F.cross_entropy(logits,target)
            margin=logits[:,3]-logits[:,:3].logsumexp(-1);good=target==3
            # Both sides retain weight; no actor/rewrite objective competes here.
            binary=.5*(F.softplus(-margin[good]).mean()+2*F.softplus(margin[~good]).mean())
            value=ce+.5*binary
        assert torch.isfinite(value);value.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],'loss':sum(losses[-50:])/len(losses[-50:]),'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==original;model.save_checkpoint(out/f'step-{step}.safetensors');replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval()
            result=evaluate(replica,model.tokenizer,'development',cache['development']if arm=='head'else None)
            novel=evaluate(replica,model.tokenizer,'novel-development',cache['novel-development']if arm=='head'else None)
            k=key(result);write(out/f'development-{step}.json',result);write(out/f'novel-development-{step}.json',novel)
            if best is None or k>best['key']:
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':k,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'step':step,'key':k,'development':brief(result),'novel':brief(novel)}),flush=True)
    model.save_checkpoint(out/'last.safetensors');assert model.input_digest()==original
    write(out/'training.json',{'steps':policy['steps'],'same_draw_digest':digest,'trainable_parameters':model.trainable_count(),'input_rows_frozen':True,'seconds':time.monotonic()-started})
    write(out/'status.json',{'phase':'trained','step':policy['steps']})


def audit(arm):
    assert(ROOT/'preselected.json').exists();metadata=json.loads((ROOT/arm/'best.json').read_text());agent=Agent(arm,checkpoint=ROOT/arm/'best.safetensors')
    model,_=agent.packed(ROOT/arm/'audit.mkqb');model.cuda().eval()
    for split in ['fresh','novel-fresh']:write(ROOT/arm/(split+'.json'),evaluate(model,agent.tokenizer,split))
    folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True);master=agent.merged_master();assert sum(p.numel()for p in master.parameters())==3022080
    master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf');attach(master,'q4');export(master,folder/'model.mkqb','q4')
    write(folder/'output-token-ids.json',DIAG_IDS);write(folder/'protocol.json',{'kind':'mk61-diagnosis-v1','classes':CLASSES,'class_token_ids':DIAG_IDS,'context':1024,'classification_only':True})
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','parameter_count':3022080,'packed_sha256':sha(folder/'model.mkqb'),
        'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},**metadata})
    write(ROOT/arm/'status.json',{'phase':'complete'})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','train','audit']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(161401);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    else:audit(a.arm)
