#!/usr/bin/env python3
"""Require byte-identical LVP and ordinary C9 cached LBV2 images; no device I/O."""
import argparse
import hashlib
from pathlib import Path
import struct
import zlib

def compare(package,cache):
    data=package.read_bytes()
    assert data[:4]==b'LVP1' and struct.unpack_from('<I',data,8)[0]==len(data)
    assert zlib.crc32(data[:28])==struct.unpack_from('<I',data,28)[0]
    assert zlib.crc32(data[32:])==struct.unpack_from('<I',data,24)[0]
    expected={}
    for i in range(struct.unpack_from('<H',data,6)[0]):
        _,offset,size,_=struct.unpack_from('<4I',data,32+i*16)
        image=data[offset:offset+size]
        expected[hashlib.sha256(image).hexdigest()]=image
    checked=[]
    for manifest in sorted(cache.glob('*/Manifest.bin')):
        m=manifest.read_bytes()
        assert len(m)==64 and m[:4]==b'LFP1' and m[4] in (0,1)
        assert zlib.crc32(m[:60])==struct.unpack_from('<I',m,60)[0]
        size=struct.unpack_from('<I',m,24)[0]
        directory=manifest.parent/f'Image{m[4]}'
        image=b''.join((directory/f'{i:08X}.bin').read_bytes() for i in range((size+1023)//1024))[:size]
        assert image[:32]==m[16:48] and image[:4]==b'LBV2'
        assert zlib.crc32(image[32:])==struct.unpack_from('<I',image,24)[0]
        digest=hashlib.sha256(image).hexdigest()
        assert digest in expected and expected[digest]==image,manifest
        checked.append(digest)
    assert checked,'no ordinary published images captured'
    return len(checked),len(set(checked)),len(expected)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path);parser.add_argument('cache',type=Path)
    args=parser.parse_args();count,unique,total=compare(args.package,args.cache)
    print(f'Ordinary/LVP bytecode: {count} manifests, {unique}/{total} unique package members byte-identical PASS')
