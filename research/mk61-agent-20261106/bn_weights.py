"""Inspect raw master parameters and the actual packed Q4 codes/scales."""
import collections
import json
import math
import re
import numpy as np
import torch
from safetensors.torch import load_file
from native_export import packet
from lowbit import unpack_codes
from bn_common import ROOT,OLD,NEW,ACTIONS,ACTION_IDS,write,check


def unpack(path):
    header,payload=packet(path);values={};codes={};scales={}
    for r in header['tensors']:
        b=payload[r['offset']:r['offset']+r['bytes']];shape=r['shape']
        if r['bits']==32:v=np.frombuffer(b,dtype='<f4').copy().reshape(shape)
        else:
            assert r['bits']==4
            c=unpack_codes(b[:r['codes_bytes']],4,math.prod(shape)).reshape(shape)
            s=np.frombuffer(b[r['codes_bytes']:],dtype='<f2').astype(np.float32).reshape(shape[0],-1,1)
            v=((c.astype(np.float32).reshape(shape[0],-1,32)-8)*s).reshape(shape);codes[r['name']]=c;scales[r['name']]=s
        values[r['name']]=torch.from_numpy(v)
    return values,codes,scales


def stats(a,b):
    a=a.double();b=b.double();d=b-a;old=float(a.norm());delta=float(d.norm())
    return {'parameters':a.numel(),'old_L2':old,'new_L2':float(b.norm()),'delta_L2':delta,
            'relative_L2':delta/old if old else None,'delta_RMS':float(d.square().mean().sqrt()),
            'max_abs_delta':float(d.abs().max()),'changed_values':int((a!=b).sum()),
            'cosine':float(torch.nn.functional.cosine_similarity(a.flatten(),b.flatten(),dim=0))if old and float(b.norm())else None}


def main():
    check();masters=[load_file(str(p/'hf/model.safetensors'))for p in [OLD,NEW]]
    packed=[unpack(p/'model.mkqb')for p in [OLD,NEW]]
    assert masters[0].keys()==masters[1].keys()==packed[0][0].keys()==packed[1][0].keys()
    records=[];groups=collections.defaultdict(list)
    for n in sorted(masters[0]):
        raw=stats(masters[0][n],masters[1][n]);q4=stats(packed[0][0][n],packed[1][0][n])
        x={'name':n,'shape':list(masters[0][n].shape),'master':raw,'effective_Q4':q4}
        if n in packed[0][1]:
            c0,c1=packed[0][1][n],packed[1][1][n];s0,s1=packed[0][2][n],packed[1][2][n]
            x.update(Q4_codes_changed=int((c0!=c1).sum()),Q4_codes_total=c0.size,
                     Q4_scales_changed=int((s0!=s1).sum()),Q4_scales_total=s0.size)
        records.append(x)
        layer=re.search(r'model.layers.(\d+)\.',n);g='layer_'+layer.group(1)if layer else n
        groups[g].append(x)
    summary={}
    for label in ['master','effective_Q4']:
        old2=sum(x[label]['old_L2']**2 for x in records);delta2=sum(x[label]['delta_L2']**2 for x in records)
        summary[label]={'parameters':sum(x[label]['parameters']for x in records),'relative_L2':math.sqrt(delta2/old2),'delta_L2':math.sqrt(delta2),
                        'changed_values':sum(x[label]['changed_values']for x in records)}
    summary['Q4_codes_changed']=sum(x.get('Q4_codes_changed',0)for x in records)
    summary['Q4_codes_total']=sum(x.get('Q4_codes_total',0)for x in records)
    summary['Q4_scales_changed']=sum(x.get('Q4_scales_changed',0)for x in records)
    summary['Q4_scales_total']=sum(x.get('Q4_scales_total',0)for x in records)
    action=[]
    for name,index in zip(ACTIONS,ACTION_IDS):
        action.append({'action':name,'token_id':index,'master':stats(masters[0]['model.embed_tokens.weight'][index],masters[1]['model.embed_tokens.weight'][index]),
                       'effective_Q4':stats(packed[0][0]['model.embed_tokens.weight'][index],packed[1][0]['model.embed_tokens.weight'][index])})
    aggregate={}
    for g,items in groups.items():
        aggregate[g]={label:{'relative_L2':math.sqrt(sum(x[label]['delta_L2']**2 for x in items)/sum(x[label]['old_L2']**2 for x in items)),
                            'delta_L2':math.sqrt(sum(x[label]['delta_L2']**2 for x in items))}for label in ['master','effective_Q4']}
    write(ROOT/'weight-statistics.json',{'summary':summary,'groups':aggregate,'actions':action,'tensors':records,'optimizer_updates':0,
          'warning':'Magnitude of drift is not causal attribution of behavior. Q4 value changes include group-scale drift even when integer codes stay equal.'})
    print(json.dumps({'summary':summary,'top_relative_Q4':sorted(records,key=lambda x:x['effective_Q4']['relative_L2']or 0,reverse=True)[:4],'actions':action}),flush=True)


if __name__=='__main__':torch.set_num_threads(2);main()
