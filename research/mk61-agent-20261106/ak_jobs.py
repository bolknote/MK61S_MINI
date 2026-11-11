"""Feature extraction, small Q4 action-head updates, and sealed closed-loop exams."""
import argparse
import collections
import copy
import json
import math
import random
import shutil
import time
import torch
import torch.nn.functional as F
from safetensors.torch import save_file,load_file
from ak_common import ROOT,HERE,PARENT,INITIAL,INITIAL_PACKET,ARMS,PANELS,ACTIONS,ACTION_IDS,CORRECT_IDS,body_ids,output_ids,compact_head,read,write,sha
from ak_model import load,set_heads
from ak_eval import panel,generate
from ac_protocol import prompt_ids,header_ids
from af_model import aligned_q4
from native_quant import attach,export
from native_export import packet


def evaluate(model,tokenizer,split):
    return{name:panel(model,tokenizer,read(ROOT/tasks.format(split=split)),read(ROOT/seeds.format(split=split)))[0]for name,tasks,seeds in PANELS}


def brief(result):return{k:{n:v for n,v in p.items()if n not in ['details','calibration']}for k,p in result.items()}


def score(result,base):
    retained=all(p['passed']>=base[n]['passed']and p['false_DONE']<=base[n]['false_DONE']and p['correct_controls_completed']>=base[n]['correct_controls_completed']for n,p in result.items())
    utility=sum(w*(result[n]['passed']-4*result[n]['false_DONE'])/result[n]['total']for n,w in [('main',.6),('skills',.25),('completion',.15)])
    return[retained,utility,-sum(p['false_DONE']for p in result.values()),sum(p['passed']for p in result.values())]


def preflight():
    f=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==f['source_master_sha256']and sha(INITIAL_PACKET)==f['source_packet_sha256']
    model,tokenizer=load();w=model.get_input_embeddings().weight.detach()[ACTION_IDS].clone();model.cpu();attach(model,'q4');export(model,ROOT/'preflight.mkqb','q4')
    assert packet(ROOT/'preflight.mkqb')[1]==packet(INITIAL_PACKET)[1]
    del model;model,tokenizer=load()
    for action in ['write','run']:assert not(set(header_ids(tokenizer,action))&set(ACTION_IDS+CORRECT_IDS))
    write(ROOT/'status.json',{'phase':'baseline_development'})
    base=evaluate(model,tokenizer,'development');write(ROOT/'initial-development.json',base)
    rows=read(ROOT/'training-states.jsonl');features=[];targets=[];ready=[];groups=[];fit=[]
    for at in range(0,len(rows),32):
        chunk=rows[at:at+32];encoded=[prompt_ids(tokenizer,r['prompt'])for r in chunk]
        keep=[i for i,p in enumerate(encoded)if len(p)<1016]
        if not keep:continue
        values=[encoded[i]for i in keep];assert all(not(set(p)&set(ACTION_IDS+CORRECT_IDS))for p in values)
        n=max(map(len,values));ids=torch.zeros((len(values),n),dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
        for j,p in enumerate(values):ids[j,:len(p)]=torch.tensor(p,device='cuda');mask[j,:len(p)]=1
        with torch.inference_mode():h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state;last=h[torch.arange(len(ids),device='cuda'),mask.sum(1)-1].float().cpu()
        features.append(last)
        for i in keep:
            r=chunk[i];targets.append(ACTIONS.index(r['action']));ready.append(bool(r['correctness']and r.get('eligible_for_DONE')and r['action']=='done'));groups.append(r['risk_group']);fit.append(at+i)
        if at%1024==0:write(ROOT/'status.json',{'phase':'frozen_features','rows':at,'total':len(rows)})
    h=torch.cat(features);target=torch.tensor(targets);ok=torch.tensor(ready,dtype=torch.bool)
    cache={'hidden':h,'target':target,'ready':ok,'groups':groups,'original_heads':w.cpu(),'rows':fit}
    torch.save(cache,ROOT/'features.pt')
    # All classifiers must start at the real source Q4 grid. Test finite
    # gradients without an optimizer update and preserve the encoder exactly.
    q=w.detach().clone().requires_grad_(True);v=F.cross_entropy(F.linear(h[:64].cuda(),aligned_q4(q)),target[:64].cuda());v.backward();assert torch.isfinite(q.grad).all()
    excluded={'ak_remote.py','ak_collect.py','ak_verify.py','ak_report.py','ak_chat.py'}
    names=[p.name for p in HERE.glob('ak_*.py')if p.name not in excluded]
    parent=json.loads((PARENT/'prepared.json').read_text())
    for n,d in parent['source_hashes'].items():assert sha(HERE/n)==d,n
    names=sorted(set(names+list(parent['source_hashes'])+['aj_common.py','aj_teacher.py','aj_model.py']))
    source=ROOT/'training-source';source.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,source/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in source.iterdir()},
      'feature_sha256':sha(ROOT/'features.pt'),'source_Q4_payload_exact':True,'private_action_rows_never_inputs_or_body':True,
      'only_128_or_640_head_parameters_trainable':True,'preflight_optimizer_updates':0,'finite_head_gradient':True,'feature_rows':len(h),
      'groups':dict(collections.Counter(groups))})
    print(json.dumps({'preflight':'passed','frozen_feature_rows':len(h),'groups':dict(collections.Counter(groups))}),flush=True)


def train(arm):
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    assert sha(ROOT/'features.pt')==prepared['feature_sha256']
    data=torch.load(ROOT/'features.pt',map_location='cpu',weights_only=True);h=data['hidden'].cuda();targets=data['target'].cuda();ready=data['ready'].cuda();original=data['original_heads'].cuda()
    offset=torch.nn.Parameter(torch.zeros(128 if arm=='done'else(5,128),device='cuda'));optimizer=torch.optim.AdamW([offset],lr=policy['lr'],weight_decay=0.)
    selector=torch.zeros((5,1),device='cuda');selector[ACTIONS.index('done')]=1
    pools={n:[i for i,g in enumerate(data['groups'])if g==n]for n in policy['quotas']};assert all(pools.values())
    rng=random.Random(131410);out=ROOT/arm;out.mkdir(exist_ok=True);base=json.loads((ROOT/'initial-development.json').read_text())
    save_file({'heads':original.cpu()},str(out/'best.safetensors'));write(out/'best.json',{'step':0,'key':score(base,base),'sha256':sha(out/'best.safetensors')})
    model,tokenizer=load();digest='00'*32;counts=collections.Counter();started=time.monotonic();research=None
    def master():return original+(selector*offset[None,:]if arm=='done'else offset)
    for step in range(1,policy['steps']+1):
        draws=[]
        for group,n in policy['quotas'].items():draws+=rng.choices(pools[group],k=n);counts[group]+=n
        digest=__import__('hashlib').sha256(bytes.fromhex(digest)+json.dumps(draws,separators=(',',':')).encode()).hexdigest()
        ids=torch.tensor(draws,device='cuda');x=h[ids];target=targets[ids];ok=ready[ids]
        optimizer.zero_grad(set_to_none=True);weight=aligned_q4(master());logits=F.linear(x,weight).float();old=F.linear(x,original).detach()
        ce=F.cross_entropy(logits,target);bad=~ok;others=[i for i,a in enumerate(ACTIONS)if a!='done']
        risk=(logits[bad].logsumexp(-1)-logits[bad][:,others].logsumexp(-1)).mean()
        safe=old.argmax(-1)==target;kl=F.kl_div(logits[safe].log_softmax(-1),old[safe].softmax(-1),reduction='batchmean')if safe.any()else logits.sum()*0
        distance=(master()-original).square().mean();value=ce+policy['false_DONE_weight']*risk+policy['keep_weight']*kl+policy['head_distance_weight']*distance
        assert torch.isfinite(value);value.backward();torch.nn.utils.clip_grad_norm_([offset],1.);optimizer.param_groups[0]['lr']=policy['lr']*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2);optimizer.step()
        if step%100==0:write(out/'status.json',{'phase':'head_training','step':step,'steps':policy['steps'],'loss':float(value.detach()),'risk':float(risk.detach()),'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            with torch.no_grad():heads=master().detach().clone()
            save_file({'heads':heads.cpu()},str(out/f'heads-{step}.safetensors'));set_heads(model,heads)
            result=evaluate(model,tokenizer,'development');key=score(result,base);write(out/f'development-{step}.json',result)
            best=json.loads((out/'best.json').read_text())
            if key>best['key']:
                save_file({'heads':heads.cpu()},str(out/'best.safetensors'));write(out/'best.json',{'step':step,'key':key,'sha256':sha(out/'best.safetensors')})
            if research is None or key[1:]>research['key'][1:]:
                save_file({'heads':heads.cpu()},str(out/'research.safetensors'));research={'step':step,'key':key,'sha256':sha(out/'research.safetensors')};write(out/'research.json',research)
            write(out/'status.json',{'phase':'controlled','step':step,'steps':policy['steps'],'key':key,'summary':brief(result)})
            print(json.dumps({'arm':arm,'step':step,'key':key,'summary':brief(result)}),flush=True)
    write(out/'training.json',{'arm':arm,'steps':policy['steps'],'trainable_parameters':offset.numel(),'same_draw_digest':digest,'counts':dict(counts),
        'generator_frozen':True,'seconds':time.monotonic()-started});write(out/'status.json',{'phase':'trained','step':policy['steps']})


def export_profile(model,tokenizer,heads,folder,role,metadata):
    folder.mkdir(parents=True,exist_ok=True);set_heads(model,heads);model.save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf')
    attach(model,'q4');export(model,folder/'model.mkqb','q4');write(folder/'output-token-ids.json',output_ids(tokenizer))
    protocol=json.loads((PARENT/'export/lr10-terminal/protocol.json').read_text());write(folder/'protocol.json',protocol)
    write(folder/'manifest.json',{'role':role,'parameter_count':3022080,'quantization_mode':'q4','source_sha256':sha(INITIAL_PACKET),'packet_sha256':sha(folder/'model.mkqb'),
        'frozen_generator':True,'changed_rows':ACTION_IDS,**metadata})


def audit(arm):
    assert(ROOT/'preselected.json').exists()
    for name in ['best','research']:
        out=ROOT/arm;heads=load_file(str(out/(name+'.safetensors')))['heads'];model,tokenizer=load(heads=heads)
        report=evaluate(model,tokenizer,'fresh');write(out/(name+'-fresh.json'),report)
        master,tokenizer=load('cpu');export_profile(master,tokenizer,heads,ROOT/'export'/(arm+('-research'if name=='research'else'')),name,json.loads((out/(name+'.json')).read_text()))
        del model,master;torch.cuda.empty_cache()
    write(out/'status.json',{'phase':'complete'})


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','train','baseline','audit']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.manual_seed(131401)
    if a.action=='prepare':preflight()
    elif a.action=='train':train(a.arm)
    elif a.action=='audit':audit(a.arm)
    else:
        assert(ROOT/'preselected.json').exists();model,tokenizer=load();write(ROOT/'initial-fresh.json',evaluate(model,tokenizer,'fresh'))


if __name__=='__main__':main()
