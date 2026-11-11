#!/usr/bin/env python3
"""Check complete lossless MKA roundtrips and unchanged tokenizer/scales."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/apps/mk61ai'))
from repack_model import repack

def seal(raw):
    struct.pack_into('<I',raw,116,zlib.crc32(raw[128:]));struct.pack_into('<I',raw,124,zlib.crc32(raw[:124]))
    return bytes(raw)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);a=p.parse_args()
    raw=a.model.read_bytes();h=struct.unpack_from('<32I',raw);count=2+11*h[4]
    linear,_=repack(raw,'linear');hybrid,changed=repack(raw,'hybrid');lut,_=repack(raw,'lut')
    assert repack(hybrid,'linear')[0]==linear and repack(lut,'linear')[0]==linear
    assert repack(hybrid,'hybrid')[0]==hybrid and repack(lut,'hybrid')[0]==hybrid
    metadata=min(h[i] for i in (16,17,19,20,22,24,26))
    assert hybrid[metadata:]==raw[metadata:]
    assert struct.unpack_from('<25I',hybrid,8)==h[2:27]
    eligible=0
    for i in range(count):
        t=struct.unpack_from('<8I',raw,h[15]+32*i);u=struct.unpack_from('<8I',hybrid,h[15]+32*i)
        assert t[:3]==u[:3] and t[4:]==u[4:]
        rows,cols,bits,grid,data,scale,size,scales=t
        assert raw[scale:scale+scales]==hybrid[scale:scale+scales]
        if bits==32:assert raw[data:data+size]==hybrid[data:data+size]
        else:
            assert bool(u[3]&256)==(bits==4 and cols==128)
            eligible+=bits==4 and cols==128
            if cols!=128:assert not (u[3]&256)
    # Exercise Q2/Q3 bit widths and byte boundaries independently of the
    # current Q4 checkpoint by changing one valid tensor's code descriptor.
    for bits in (2,3):
        source=bytearray(linear);rows,cols=struct.unpack_from('<2I',source,h[15])
        struct.pack_into('<2I',source,h[15]+8,bits,1)
        struct.pack_into('<I',source,h[15]+24,rows*cols*bits//8)
        source=seal(source);planes,_=repack(source,'lut')
        assert repack(planes,'linear')[0]==source
    for offset in (0,124,130,len(raw)-1):
        corrupt=bytearray(raw);corrupt[offset]^=1
        try:repack(bytes(corrupt))
        except ValueError:pass
        else:raise AssertionError('Corrupt CRC accepted')
    corrupt=bytearray(raw);struct.pack_into('<I',corrupt,h[15]+16,h[15])
    try:repack(seal(corrupt))
    except ValueError:pass
    else:raise AssertionError('Metadata overlap accepted')
    print('MKA repack PASS:',eligible,'eligible tensors;',len(changed),'changed; all weights/scales/tokenizer/RoPE exact; Q2/Q3 roundtrip and corruption guards PASS')
    print('Hybrid SHA256:',hashlib.sha256(hybrid).hexdigest())
if __name__=='__main__':main()
