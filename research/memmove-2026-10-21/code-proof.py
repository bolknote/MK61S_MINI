#!/usr/bin/env python3
"""Verify the same memmove body in benchmark APPs and full resident firmware."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work',type=Path,default=ROOT/'.build/memmove-20261021')
a=p.parse_args()
items=[('m4_flash','m4-v3-flash/payload.elf','memmove'),
       ('m4_app','m4-v3-app/app/MOVEBEN.elf','memmove'),
       ('f411','classic-build/resident.elf','memmove'),
       ('f401','f401-build/resident.elf','memmove'),
       ('pico','pico-build/mk61s-picocalc-pico-h.elf','__wrap_memmove'),
       ('m0_app','m0-final-app/app/MOVEBEN.elf','memmove'),
       ('m0_shared_target','m0-shared-app/app/MOVEBEN.elf','own64')]
proof={}
for tag,path,name in items:
    file=a.work/path;e=ElfImage(file);raw=file.read_bytes()
    def read(address,size):
        sec=next(s for s in e.sections if s[1]!=8 and s[3]<=address and address+size<=s[3]+s[5])
        offset=sec[4]+address-sec[3]
        return raw[offset:offset+size]
    address=e.symbols[name]&~1;size=e.sizes[name]
    proof[tag]=dict(address=hex(address|1),bytes=size,code_sha256=hashlib.sha256(read(address,size)).hexdigest(),elf_sha256=hashlib.sha256(raw).hexdigest())
    if tag in ('f411','f401','pico'):
        runtime='_ZN8picocalc14native_runtimeE' if tag=='pico' else '_ZN15loadable_module12_GLOBAL__N_1L7runtimeE'
        pointer=struct.unpack('<I',read(e.symbols[runtime]+24*4,4))[0]
        assert pointer==(address|1),(tag,hex(pointer),hex(address))
        proof[tag]['runtime_slot_24']=hex(pointer)
for family in (('m4_flash','m4_app','f411','f401'),('pico','m0_app','m0_shared_target')):
    assert len({proof[tag]['code_sha256'] for tag in family})==1,family
proof['sources']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
    ('code/memory_move_arm.h','code/memmove_m0.inc','code/memmove_m4.inc','sdk/portable/memory.c',
     'code/system_memory_fill_move.c','ports/picocalc/memory.c')}
(a.work/'code-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('M4 APP/Flash/F411/F401 and M0 APP/shared/Pico bodies identical; runtime slot 24 PASS')
