#!/usr/bin/env python3
"""Losslessly repack an exported MKA; never requantize or change token IDs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

def repack(raw, layout='hybrid'):
    if layout not in ('hybrid', 'linear', 'lut'):
        raise ValueError('Unknown packing')
    if len(raw)<128 or raw[:8]!=b'M61AI01\0':
        raise ValueError('Expected M61AI01')
    h=struct.unpack_from('<32I',raw)
    if h[2]!=1 or h[3]!=len(raw) or h[31]!=zlib.crc32(raw[:124]) or h[29]!=zlib.crc32(raw[128:]):
        raise ValueError('Invalid size/version/CRC')
    count=2+11*h[4];table=h[15];end=table+count*32
    metadata=min(h[i] for i in (16,17,19,20,22,24,26))
    if not 128<=table<end<=metadata<=len(raw):
        raise ValueError('Invalid exported tensor region')
    tensors=[struct.unpack_from('<8I',raw,table+i*32) for i in range(count)]
    regions=[(table,end)];out=bytearray(raw);changed=[]
    for i,(rows,cols,bits,grid,data,scale,size,scales) in enumerate(tensors):
        if not rows or not cols:
            raise ValueError('Empty tensor')
        if bits==32:
            valid=grid==0 and rows==1 and size==cols*4 and scales==0
        else:
            valid=(bits in (2,3,4) and cols%32==0 and size==rows*cols*bits//8
                   and scales==rows*cols//16 and grid in ((0,256) if bits==4 else (1,257)))
        if not valid:
            raise ValueError('Invalid tensor shape/packing')
        for at,n in ((data,size),(scale,scales)):
            if n:
                if at<end or at+n>metadata:
                    raise ValueError('Tensor overlaps non-weight metadata')
                regions.append((at,at+n))
        if bits==32:continue
        planes=layout=='lut' or (layout=='hybrid' and bits==4 and cols==128)
        if planes==bool(grid&256):continue
        width=bits*4
        for offset in range(data,data+size,width):
            chunk=raw[offset:offset+width]
            if grid&256:
                values=[sum(((chunk[b*4+j//8]>>(j%8))&1)<<b for b in range(bits)) for j in range(32)]
            else:
                packed=int.from_bytes(chunk,'little');values=[(packed>>(j*bits))&((1<<bits)-1) for j in range(32)]
            if planes:
                encoded=bytes(sum(((values[g*8+j]>>b)&1)<<j for j in range(8)) for b in range(bits) for g in range(4))
            else:
                encoded=sum(v<<(j*bits) for j,v in enumerate(values)).to_bytes(width,'little')
            out[offset:offset+width]=encoded
        struct.pack_into('<I',out,table+i*32+12,(grid&1)|(256 if planes else 0))
        changed.append(i)
    regions.sort()
    if any(b>c for (_,b),(c,_) in zip(regions,regions[1:])):
        raise ValueError('Overlapping tensor ranges')
    struct.pack_into('<I',out,116,zlib.crc32(out[128:]))
    struct.pack_into('<I',out,124,zlib.crc32(out[:124]))
    return bytes(out),changed

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layout',choices=('hybrid','linear','lut'),default='hybrid');a=p.parse_args()
    if a.input.resolve()==a.output.resolve():p.error('Use a separate output file')
    raw=a.input.read_bytes();packed,changed=repack(raw,a.layout)
    # The inverse must recover the complete canonical package, including CRC,
    # tokenizer/RoPE bytes and scales, not just approximate weight values.
    canonical,_=repack(raw,'linear');roundtrip,_=repack(packed,'linear')
    if canonical!=roundtrip:raise ValueError('Lossless roundtrip failed')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(packed)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    report=dict(layout=a.layout,bytes=len(packed),input_sha256=sha(raw),sha256=sha(packed),
                changed_tensors=changed,lossless_canonical_roundtrip=True)
    a.output.with_suffix('.repack.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':main()
