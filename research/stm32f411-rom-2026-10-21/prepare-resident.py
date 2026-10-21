#!/usr/bin/env python3
"""Compile the production helper and seal an isolated resident replacement."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info

def main():
    tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
    out=ROOT/'.build/stm32f411-rom-20261021/resident';out.mkdir(exist_ok=True)
    obj=out/'fill.o';helper=out/'fill.bin'
    subprocess.run([tc/'arm-none-eabi-gcc','-mcpu=cortex-m4','-mthumb','-Os','-std=c11','-Wall','-Wextra','-Werror',
        '-fno-builtin','-ffunction-sections','-DARDUINO_ARCH_STM32','-c',ROOT/'code/system_memory_fill_move.c','-o',obj],check=True)
    subprocess.run([tc/'arm-none-eabi-objcopy','-O','binary','-j','.text.mk61_memory_fill_bulk',obj,helper],check=True)
    symbol=next(line.split() for line in subprocess.check_output([tc/'arm-none-eabi-nm','-S',obj],text=True).splitlines() if line.endswith(' mk61_memory_fill_bulk'))
    size=int(symbol[1],16);raw=helper.read_bytes()[:size]
    assert size==82 and raw==(HERE/'local_bulk_style.bin').read_bytes()
    qualifications=json.loads((HERE/'production-validation.json').read_text())
    assert len(qualifications)==2 and all(q['status']=='PASS' and q['bulk_sha256']==hashlib.sha256(raw).hexdigest() for q in qualifications)
    backup=(HERE/'flash-hil-3/flash-original-a.bin').read_bytes()
    assert hashlib.sha256(backup).hexdigest()=='412f036e278a75beb63c96d95f4ca72798b59d66d6549e43e420261cafa602d1'
    original=firmware_info(HERE/'flash-hil-3/resident-original.bin')
    # The isolated image changes only the existing bulk slot and its CRC/build.
    # Short helpers, dispatcher, linked image size and every other address stay fixed.
    image=bytearray(backup[:original['bytes']]);at=0x8934
    expected=(HERE/'benchmark/resident-code.bin').read_bytes()[at-0x8800:at-0x8800+88]
    assert image[at:at+88]==expected
    image[at:at+88]=raw+b'\x00\xbf'*3
    footer=original['footer'];image[footer+20:footer+28]=bytes(8)
    crc=zlib.crc32(image);struct.pack_into('<II',image,footer+20,crc,crc)
    resident=out/'resident.bin';resident.write_bytes(image)
    info=firmware_info(resident)
    full=bytearray(backup);full[:len(image)]=image
    layout=json.loads((ROOT/'.build/stm32f411-rom-20261021/flash-experiment/layout.json').read_text())
    payload=(ROOT/'.build/stm32f411-rom-20261021/flash-experiment/payload.bin').read_bytes()
    offset=layout['base']-0x08000000
    assert full[offset:offset+len(payload)]==b'\xff'*len(payload)
    full[offset:offset+len(payload)]=payload
    path=out/'full-flash.bin';path.write_bytes(full)
    changes=[i for i,(a,b) in enumerate(zip(backup,full)) if a!=b]
    assert all(at<=i<at+88 or footer+20<=i<footer+28 or offset<=i<offset+len(payload) for i in changes)
    report={'status':'PASS','resident':info,'path':str(path),'build':info['build'],
        'helper_bytes':size,'helper_sha256':hashlib.sha256(raw).hexdigest(),
        'full_sha256':hashlib.sha256(full).hexdigest(),'full_crc32':zlib.crc32(full),
        'patched_slot':'08008934..0800898B','method':'Actual production helper extracted from GCC object; fixed existing resident function slot; same short paths/dispatcher; sealed resident CRC/build; comparison extension outside resident image.'}
    (HERE/'resident-candidate.json').write_text(json.dumps(report,indent=2)+'\n')
    (HERE/'production-memset.S').write_text(subprocess.check_output([tc/'arm-none-eabi-objdump','-d','-j','.text.mk61_memory_fill_bulk',obj],text=True))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
