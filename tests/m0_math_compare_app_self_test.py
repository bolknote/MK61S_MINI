#!/usr/bin/env python3
"""Execute the timing APP's exact C source against its real M0 math ELF.

Storage, timer and UI service callbacks are mocked. Numerical functions are
not mocked. This checks typed call/return conventions, wire layout, calibration
loops and failure reporting; the synthetic timer is not a hardware measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from build_picocalc import compiler_bin
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine,SP
from hil_m0_math_compare import decode
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC

SHIM=r'''
#include "mk61_app.h"
#define FN(type,address) ((type)(uintptr_t)(address))
const mk61_app_services services={
 .magic=MK61_APP_SERVICES_MAGIC,.version=MK61_APP_SERVICES_VERSION,.struct_size=sizeof(mk61_app_services),
 .call=FN(uint32_t(*)(uint32_t,uint32_t,uint32_t,uint32_t,void*),0x080E0011)
};
const mk61_app_api api={
 .magic=MK61_APP_API_MAGIC,.version=MK61_APP_API_VERSION,.struct_size=sizeof(mk61_app_api),
 .service=FN(void(*)(void),0x080E0051),
 .file_size=FN(uint32_t(*)(uint32_t),0x080E0031),
 .file_read=FN(uint32_t(*)(uint32_t,uint32_t,uint8_t*,uint32_t),0x080E0041),
 .query_service=FN(const void*(*)(uint32_t,uint32_t),0x080E0021)
};
const mk61_app_api* mk61_api=&api;
const mk61_service_file file_object={.id=1,.parent=MK61_SERVICE_ROOT_ID};
const uint32_t operations[]={MK61_SERVICE_CAPABILITIES,MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_FILE_WRITE,MK61_SERVICE_CAP_FILES};
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cache-counters',action='store_true')
    p.add_argument('--fixture',type=Path,help='Exact benchmark source to qualify; defaults to its frozen copy when available.')
    p.add_argument('--kinds',type=int,nargs='+',help='Explicit ABI kinds for a restricted benchmark; default requires all 13 kinds.')
    p.add_argument('--rom',type=Path,help='Captured factory ROM, required only by direct-ROM experiments.')
    p.add_argument('--rom-metadata',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    assert bool(a.rom)==bool(a.rom_metadata),'ROM bytes and verified metadata must be supplied together'
    frozen=a.benchmark/'TIMING-fixture.c'
    source_fixture=a.fixture or (frozen if frozen.is_file() else ROOT/'tests/fixtures/m0_math_compare_benchmark.c')
    round_definition=re.search(r'^#define ROUNDS (\d+)U$',source_fixture.read_text(),re.MULTILINE)
    assert round_definition and int(round_definition[1]) in (9,12),'Unsupported timing APP round count'
    rounds=int(round_definition[1])
    config=json.loads((a.benchmark/'benchmark.json').read_text());tc=compiler_bin(None)
    if not a.fixture and 'fixture_sha256' in config:
        assert hashlib.sha256(source_fixture.read_bytes()).hexdigest()==config['fixture_sha256'],'Frozen fixture changed'
    assert hashlib.sha256((a.benchmark/'firmware/mk61s-picocalc-pico-h.elf').read_bytes()).hexdigest()==config['elf_sha256'],'Math ELF changed'
    assert hashlib.sha256(Path(config['app']).read_bytes()).hexdigest()==config['app_sha256'],'Timing APP changed'
    shim=a.output/'api.c';shim.write_text(SHIM)
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=gnu11','-fno-builtin','-ffreestanding','-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code')]
    has_warmup='MK61_M0_TIMING_WARMUP_US' in source_fixture.read_text()
    if has_warmup:flags+=['-DMK61_M0_TIMING_WARMUP_US=1000']
    if a.cache_counters:flags+=['-DMK61_M0_TIMING_CACHE=1']
    objects=[]
    for source in (source_fixture,ROOT/'sdk/portable/memory.c',shim):
        obj=a.output/(source.name+'.o');objects.append(obj)
        subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-Wall','-Wextra','-Werror','-c',str(source),'-o',str(obj)],check=True)
    target=a.output/'fixture.elf'
    subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-nostdlib','-Wl,-Ttext=0x20030000','-Wl,-e,main',*[str(x) for x in objects],'-o',str(target)],check=True)
    fixture=ElfImage(target)
    cache_state={0x1400000C:0,0x14000010:0}
    def cache_traffic(amount):
        # The other core can keep hitting XIP between the two counter writes.
        # More traffic during reset than readout exposes a reversed reset pair.
        for register in cache_state:cache_state[register]+=amount
    if a.rom:
        from m0_bootrom import ROMMachine
        parent_machine=ROMMachine
    else:
        parent_machine=Machine
    class AppMachine(parent_machine):
        def write(self,uc,access,address,size,value,user):
            if a.cache_counters and address in (0x1400000C,0x14000010):
                assert size==4 and value==0
                cache_traffic(17);cache_state[address]=0;return
            if SP-32768<=address and address+size<=SP:return
            if any(s[2]&1 and s[3]<=address and address+size<=s[3]+s[5] for s in fixture.sections):return
            return super().write(uc,access,address,size,value,user)
        def rom_intrinsic(self,uc,address,size,operation):
            if operation not in ('memcpy','memset'):return super().rom_intrinsic(uc,address,size,operation)
            x,y,n=(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2))
            assert SP-32768<=x and x+n<=SP
            uc.mem_write(x,bytes([y&255])*n if operation=='memset' else bytes(uc.mem_read(y,n)))
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    m=(AppMachine(a.benchmark/'firmware/mk61s-picocalc-pico-h.elf',a.rom,a.rom_metadata) if a.rom else
       AppMachine(a.benchmark/'firmware/mk61s-picocalc-pico-h.elf',True))
    fixture.load(m.uc)
    if a.cache_counters:
        m.uc.mem_map(0x14000000,4096)
        def cache_counter(uc,access,address,size,value,user):
            assert size==4
            cache_traffic(3)
            uc.mem_write(address,struct.pack('<I',cache_state[address]))
        m.uc.hook_add(UC_HOOK_MEM_READ,cache_counter,begin=0x1400000C,end=0x14000013)
    m.elf.symbols['timing_test_entry']=fixture.symbols['main'];m.uc.mem_map(0x40054000,4096)
    operation_address=fixture.symbols['operations'];operations=struct.unpack('<4I',m.uc.mem_read(operation_address,16))
    file_address=fixture.symbols['file_object'];file_size=fixture.sizes['file_object'];file_object=bytes(m.uc.mem_read(file_address,file_size))
    source=b'';result=None;ticks=0
    def timer(uc,access,address,size,value,user):
        nonlocal ticks
        ticks+=100;uc.mem_write(address,struct.pack('<I',ticks))
    m.uc.hook_add(UC_HOOK_MEM_READ,timer,begin=0x40054028,end=0x4005402B)
    def callback(uc,address,size,user):
        nonlocal result
        r=[uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        value=0
        if address==0x080E0020:value=fixture.symbols['services']
        elif address==0x080E0030:value=len(source)
        elif address==0x080E0040:
            block=bytes(source[r[1]:r[1]+r[3]]);uc.mem_write(r[2],block);value=len(block)
        elif address==0x080E0010:
            if r[0]==operations[0]:value=operations[3]
            else:
                pointer=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4))[0]
                if r[0]==operations[1]:uc.mem_write(pointer,file_object)
                elif r[0]==operations[2]:
                    name,data,length,_=struct.unpack('<4I',uc.mem_read(pointer,16));assert bytes(uc.mem_read(name,7))==b'RESULT\0'
                    result=bytes(uc.mem_read(data,length));value=1
                else:raise AssertionError(('Unexpected service call',r))
        else:assert address==0x080E0050,address
        uc.reg_write(UC_ARM_REG_R0,value);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    for address in (0x080E0010,0x080E0020,0x080E0030,0x080E0040,0x080E0050):
        m.uc.mem_write(address,b'\x70\x47');m.uc.hook_add(UC_HOOK_CODE,callback,begin=address,end=address)
    selected={}
    for chunk in config['chunks']:selected.setdefault(chunk['kind'],chunk)
    expected_kinds=set(range(13)) if a.kinds is None else set(a.kinds)
    assert expected_kinds and expected_kinds<=set(range(13)),sorted(expected_kinds)
    assert set(selected)==expected_kinds,(sorted(selected),sorted(expected_kinds))
    rows=[]
    for kind,chunk in sorted(selected.items()):
        data=Path(chunk['input']).read_bytes();header=list(struct.unpack_from('<8I',data));count=min(2,header[4]);header[4]=count;header[5]=1
        original=struct.pack('<8I',*header)+data[32:32+24*count]
        for negative in (False,True):
            source=bytearray(original)
            if negative:source[32+16]^=1
            result=None;reached=[0,0];hooks=[]
            for i,address in enumerate(header[6:8]):
                def entered(uc,address,size,index):reached[index]+=1
                hooks.append(m.uc.hook_add(UC_HOOK_CODE,entered,i,begin=address&~1,end=address&~1))
            try:status=m.call('timing_test_entry',0)[0]&0xFFFFFFFF
            finally:
                for h in hooks:m.uc.hook_del(h)
            assert status==0 and result is not None,(kind,status)
            version=(2 if a.cache_counters else 1)+(2 if rounds==12 else 0)
            result_offset=40+16*rounds+(32*rounds if a.cache_counters else 0)
            h=struct.unpack_from('<10I',result);assert h[:7]==(0x4D305250,version,header[2],kind,count,1,rounds),h
            assert h[7]==int(negative) and h[8]==(0 if negative else 0xFFFFFFFF),h
            assert len(result)==result_offset+16*count
            # The synthetic timer advances100 us per read: the1000-us
            # warm-up has9passes, in addition to verification and timed rounds.
            passes=1+(9 if has_warmup else 0)+rounds
            assert reached==[count*passes,count*passes],(kind,reached)
            assert h[9]==(1000 if has_warmup else 0),h
            assert struct.unpack_from('<'+'I'*(4*rounds),result,40)==(100,)*(4*rounds)
            for i in range(count):assert struct.unpack_from('<Q',result,result_offset+16*i)[0]==struct.unpack_from('<Q',original,32+24*i+16)[0]
            if not negative:
                parsed=decode(result,dict(chunk,cases=count,loops=1),original)
                if a.cache_counters:
                    assert all(v['cache']['median_misses_per_call']==0 and v['cache']['median_accesses_per_call']==0 for v in parsed['timings'].values())
            rows.append(dict(kind=kind,operation=chunk['operation'],negative=negative,calls=reached))
            print('PASS',kind,chunk['operation'],'failure detected' if negative else 'exact results',flush=True)
    report=dict(status='PASS',cases=rows,cache_counters=a.cache_counters,warmup_tested=has_warmup,
        rounds=rounds,wire_version=version,
        tested_kinds=sorted(selected),all_abi_kinds_tested=expected_kinds==set(range(13)),
        scope='Real ARM math and timing APP source. Timer/storage/UI/XIP counters mocked; this is a protocol and ABI test, not a cycle benchmark.')
    if a.rom:
        report['rom_sha256']=hashlib.sha256(a.rom.read_bytes()).hexdigest()
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
