#!/usr/bin/env python3
"""Prepare a memchr payload; installation requires a separate verified handoff."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zlib

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
p.add_argument('--cpu',choices=('m0','m4'),required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('kernels',HERE/'build-kernels.py')
kernels=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernels)
base=0x08062000 if a.cpu=='m4' else 0x101e0000
layout=kernels.build(a.arm_toolchain_bin,out,a.cpu,base)
code=(out/'kernels.bin').read_bytes();assert len(code)<0xf00
data=bytearray([0xa5]*4112)
# Different values have known first appearances, from byte zero to byte 4095.
for value,at in enumerate((0,1,3,4,7,15,16,63,64,255,256,1023,4095),0x10):data[at]=value
raw=code+b'\xff'*(0xf00-len(code))+data
assert len(raw)<=8192
(out/'payload.bin').write_bytes(raw)
layout.update(base=base,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),crc32=zlib.crc32(raw),
    code_bytes=len(code),code_sha256=hashlib.sha256(code).hexdigest(),
    data_address=base+0xf00,data_sha256=hashlib.sha256(data).hexdigest())
(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
(out/'flash-layout.h').write_text('\n'.join('#define FLASH_'+name.upper()+' '+str(row['address'])+'u' for name,row in layout['functions'].items())+
    f'\n#define PAYLOAD_BASE {base}u\n#define PAYLOAD_BYTES {len(raw)}u\n#define PAYLOAD_CRC {zlib.crc32(raw)}u\n#define PAYLOAD_DATA {base+0xf00}u\n')
print(json.dumps(layout,indent=2))
