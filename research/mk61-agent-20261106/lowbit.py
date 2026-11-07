"""A small, inspectable 2/3/4-bit baseline with real packing and STE QAT.

This is uniform per-32-group quantization, not ParetoQ, GPTQ or a native kernel.
Q4 uses the existing signed zero-containing grid; Q2/Q3 use a full symmetric
mid-rise grid. A completely zero group stays zero. Norm vectors stay FP32.
"""
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import torch
from torch.nn.utils import parametrize
from quantization import quantize_matrix

MAGIC=b'MKQBv1\0\0'
FORMATS=['q4','q3','q2','mixed']


def bits_for(name,mode):
    if mode not in FORMATS:raise ValueError(mode)
    return (2 if '.mlp.'in name else 4)if mode=='mixed'else int(mode[1])


def quantize(weight,bits):
    if bits==4:
        codes,scale=quantize_matrix(weight)
        return (codes+8).to(torch.uint8),scale,(codes*scale).reshape_as(weight)
    if bits not in [2,3]or weight.ndim!=2 or weight.shape[-1]%32:raise ValueError('Unsupported matrix')
    groups=weight.float().reshape(weight.shape[0],-1,32)
    scale=groups.abs().amax(-1,keepdim=True).to(torch.float16).float()
    maximum=(1<<bits)-1
    codes=((groups/scale.clamp_min(2**-24)+1)*(maximum/2)).round().clamp(0,maximum)
    decoded=(codes*(2/maximum)-1)*scale
    return codes.to(torch.uint8),scale,decoded.reshape_as(weight)


def fake(weight,bits):
    value=quantize(weight,bits)[2].to(weight.dtype)
    return weight+(value-weight).detach()


class LowBitWeight(torch.nn.Module):
    def __init__(self,bits):super().__init__();self.bits=bits
    def forward(self,value):return fake(value,self.bits)


def attach(model,mode):
    # Tied output weights are the same Parameter; the identical quantizer must
    # cover the embedding and the linear output projection.
    for name,module in list(model.named_modules()):
        if isinstance(module,(torch.nn.Linear,torch.nn.Embedding)):
            if module.weight.ndim!=2 or module.weight.shape[-1]%32:raise ValueError(name)
            parametrize.register_parametrization(module,'weight',LowBitWeight(bits_for(name+'.weight',mode)))


def pack_codes(codes,bits):
    flat=codes.cpu().numpy().reshape(-1)
    binary=((flat[:,None]>>np.arange(bits,dtype=np.uint8))&1).reshape(-1)
    return np.packbits(binary,bitorder='little').tobytes()


def unpack_codes(data,bits,count):
    binary=np.unpackbits(np.frombuffer(data,dtype=np.uint8),bitorder='little')[:count*bits].reshape(count,bits)
    return (binary.astype(np.uint16)*(1<<np.arange(bits,dtype=np.uint16))).sum(1).astype(np.uint8)


@torch.no_grad()
def export(model,path,mode):
    path=Path(path);chunks=[];records=[];offset=0
    for name,p in model.named_parameters():
        value=p.detach().cpu().float().contiguous()
        if value.ndim==2:
            bits=bits_for(name,mode);codes,scales,_=quantize(value,bits)
            packed=pack_codes(codes,bits);chunk=packed+scales.to(torch.float16).numpy().tobytes()
            record={'name':name,'shape':list(value.shape),'bits':bits,'codes_bytes':len(packed)}
        else:
            chunk=value.numpy().tobytes();record={'name':name,'shape':list(value.shape),'bits':32}
        record.update(offset=offset,bytes=len(chunk));records.append(record);chunks.append(chunk);offset+=len(chunk)
    header=json.dumps({'format':'MKQBv1','mode':mode,'group':32,'config':model.config.to_dict(),
      'q4_grid':'signed -7..7, zero included','q2_q3_grid':'symmetric uniform midrise, zero groups preserved',
      'tensors':records},separators=(',',':')).encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(MAGIC+struct.pack('<I',len(header))+header+b''.join(chunks))
    return {'file':str(path),'bytes':path.stat().st_size,'payload_bytes':offset,'mode':mode,
      'parameters':sum(p.numel()for p in model.parameters()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


@torch.no_grad()
def load(model,path):
    data=Path(path).read_bytes()
    if data[:8]!=MAGIC:raise ValueError('Invalid MKQBv1 magic')
    size=struct.unpack('<I',data[8:12])[0];header=json.loads(data[12:12+size]);payload=memoryview(data)[12+size:]
    seen=set();offset=0
    for row in header['tensors']:
        name=row['name'];shape=row['shape'];p=model.get_parameter(name)
        if name in seen or list(p.shape)!=shape or row['offset']!=offset:raise ValueError('Invalid tensor coverage')
        offset+=row['bytes']
        if offset>len(payload):raise ValueError('Truncated tensor')
        chunk=payload[row['offset']:offset];bits=row['bits']
        if bits==32:value=torch.from_numpy(np.frombuffer(chunk,dtype='<f4').copy()).reshape(shape)
        else:
            count=int(np.prod(shape));codes=torch.from_numpy(unpack_codes(chunk[:row['codes_bytes']],bits,count).copy()).float().reshape(shape[0],-1,32)
            scales=torch.from_numpy(np.frombuffer(chunk[row['codes_bytes']:],dtype='<f2').copy()).float().reshape(shape[0],-1,1)
            value=((codes-8)*scales if bits==4 else(codes*(2/((1<<bits)-1))-1)*scales).reshape(shape)
        p.copy_(value.to(p.device,p.dtype));seen.add(name)
    if offset!=len(payload)or seen!={n for n,_ in model.named_parameters()}:raise ValueError('Incomplete packed model')
    return header
