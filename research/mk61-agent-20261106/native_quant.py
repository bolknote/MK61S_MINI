"""Target-format QAT with learned Q2 group amplitudes and exact MKQB export.

Learned amplitude / gradient scaling are LSQ-inspired, adapted to symmetric
per-32 mid-rise weight groups. This is not a reproduction of the LSQ paper.
Master weights and scale parameters are training state, not extra device weights.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct

import torch
from torch.nn.utils import parametrize
from safetensors.torch import load_file,save_file
from transformers import AutoModelForCausalLM

from quantization import fake_q4,quantize_matrix
from lowbit import MAGIC,pack_codes,load


@torch.no_grad()
def initial_amplitude(weight):
    w=weight.float().reshape(weight.shape[0],-1,32)
    maximum=w.abs().amax(-1,keepdim=True).clamp_min(2**-20)
    best=maximum.clone();best_error=torch.full_like(maximum,float('inf'))
    for ratio in [.55,.7,.85,1.,1.15]:
        amplitude=(maximum*ratio).to(torch.float16).float()
        codes=((w/amplitude.clamp_min(2**-24)+1)*1.5).round().clamp(0,3)
        rounded=(codes*(2/3)-1)*amplitude
        error=(rounded-w).square().mean(-1,keepdim=True)
        choose=error<best_error;best=torch.where(choose,amplitude,best);best_error=torch.minimum(error,best_error)
    return best


class Fixed4(torch.nn.Module):
    def forward(self,weight):return fake_q4(weight)


class Learned2(torch.nn.Module):
    def __init__(self,weight):
        super().__init__();self.log_scale=torch.nn.Parameter(initial_amplitude(weight).log())

    def amplitude(self):
        # Scale the parameter gradient without changing the forward value.
        x=self.log_scale/math.sqrt(32)+(self.log_scale-self.log_scale/math.sqrt(32)).detach()
        value=x.exp().clamp(2**-24,32768)
        return value+(value.to(torch.float16).float()-value).detach()

    def forward(self,weight):
        w=weight.reshape(weight.shape[0],-1,32);amp=self.amplitude()
        bounded=(w/amp).clamp(-1,1)
        code=((bounded+1)*1.5).round().clamp(0,3);grid=code*(2/3)-1
        value=(bounded+(grid-bounded).detach())*amp
        return value.reshape_as(weight).to(weight.dtype)


def attach(model,mode):
    if mode not in ['q4','mixed']:raise ValueError(mode)
    for name,module in list(model.named_modules()):
        if isinstance(module,(torch.nn.Linear,torch.nn.Embedding)):
            assert module.weight.shape[-1]%32==0
            quantizer=Learned2(module.weight.detach())if mode=='mixed'and'.mlp.'in name else Fixed4()
            parametrize.register_parametrization(module,'weight',quantizer)


@torch.no_grad()
def plain_master(model):
    with torch.random.fork_rng(devices=[]):
        replica=AutoModelForCausalLM.from_config(copy.deepcopy(model.config),trust_remote_code=False).cpu()
    seen=set()
    for name,parameter in model.named_parameters():
        if name.endswith('.log_scale'):continue
        name=name.replace('.parametrizations.weight.original','.weight')
        replica.get_parameter(name).copy_(parameter.detach().cpu());seen.add(name)
    assert seen=={n for n,_ in replica.named_parameters()}
    replica.tie_weights();return replica.eval()


def scale_state(model):
    return {name:module.log_scale.detach().cpu().contiguous()for name,module in model.named_modules()if isinstance(module,Learned2)}


def restore_scales(model,directory):
    path=Path(directory)/'quant-scales.safetensors'
    if not path.exists():return
    state=load_file(str(path));expected=scale_state(model)
    if set(state)!=set(expected):raise ValueError('Learned scale coverage differs')
    with torch.no_grad():
        for name,value in state.items():model.get_submodule(name).log_scale.copy_(value.to(next(model.parameters()).device))


def save(model,tokenizer,directory,mode):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    replica=plain_master(model);replica.save_pretrained(directory,safe_serialization=True);tokenizer.save_pretrained(directory)
    state=scale_state(model)
    if state:save_file(state,str(directory/'quant-scales.safetensors'))
    (directory/'precision.json').write_text(json.dumps({'mode':mode,'group':32,'scale_storage':'FP16 at inference',
      'learned_scale_parameters':sum(v.numel()for v in state.values()),'inference_weight_parameters':sum(p.numel()for p in replica.parameters()),
      'qat_from_first_step':True},indent=2)+'\n')


@torch.no_grad()
def export(model,path,mode):
    path=Path(path);replica=plain_master(model);records=[];chunks=[];offset=0
    for name,p in replica.named_parameters():
        w=p.float().contiguous()
        if w.ndim==2:
            module=model.get_submodule(name.rsplit('.',1)[0]);quantizer=module.parametrizations.weight[0]
            if isinstance(quantizer,Learned2):
                bits=2;amp=quantizer.amplitude().detach().cpu()
                codes=((w.reshape(w.shape[0],-1,32)/amp+1)*1.5).round().clamp(0,3).to(torch.uint8)
            else:
                bits=4;q,amp=quantize_matrix(w);codes=(q+8).to(torch.uint8)
            packed=pack_codes(codes,bits);chunk=packed+amp.to(torch.float16).numpy().tobytes()
            record={'name':name,'shape':list(w.shape),'bits':bits,'codes_bytes':len(packed)}
        else:chunk=w.numpy().tobytes();record={'name':name,'shape':list(w.shape),'bits':32}
        record.update(offset=offset,bytes=len(chunk));offset+=len(chunk);records.append(record);chunks.append(chunk)
    header=json.dumps({'format':'MKQBv1','mode':mode,'group':32,'config':replica.config.to_dict(),
      'q2_grid':'symmetric uniform midrise with learned amplitude','q4_grid':'signed -7..7',
      'tensors':records},separators=(',',':')).encode()
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(MAGIC+struct.pack('<I',len(header))+header+b''.join(chunks))
    return {'file':str(path),'bytes':path.stat().st_size,'payload_bytes':offset,'parameters':sum(p.numel()for p in replica.parameters()),
      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mode':mode,'learned_group_scale_count':sum(v.numel()for v in scale_state(model).values())}


def packed_copy(model,path,mode):
    report=export(model,path,mode);replica=plain_master(model);load(replica,path)
    return replica,report
