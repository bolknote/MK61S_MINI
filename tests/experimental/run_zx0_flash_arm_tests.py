import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_CPU_ARM_CORTEX_M4,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R4,UC_ARM_REG_R11,UC_ARM_REG_XPSR

parser=argparse.ArgumentParser(description='Validate actual normal Flash ELF prepare/emit, bounds, bytes and ABI; no cycle claim.')
parser.add_argument('--manifest',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--arm-toolchain-bin',type=Path,required=True)
args=parser.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
fixture=json.loads(args.manifest.read_text())
command=[args.arm_toolchain_bin/'arm-none-eabi-g++','-std=c++17','-Os','-mcpu=cortex-m4','-mthumb',
    '-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-fno-builtin','-fno-exceptions','-fno-rtti','-nostdlib',
    '-Wl,-Ttext=0x080F0000,-e,flash_probe','-I'+str(ROOT/'code'),
    ROOT/'tests/experimental/zx0_flash_arm_probe.cpp','-o',out/'probe.elf']
subprocess.run(list(map(str,command)),check=True)
probe=ElfImage(out/'probe.elf')
A,B,C,J,SP,STOP=0x20008000,0x2000A000,0x2000C000,0x2000D000,0x2001F000,0x080FF000
header=(args.manifest.parent/'zx0_bench_fixture.hpp').read_text()
source=bytes(map(int,re.search(r'source_fixture\[\]=\{([^}]+)',header)[1].split(',')))
image=bytes(map(int,re.search(r'image_fixture\[\]=\{([^}]+)',header)[1].split(',')))
machines=[]
for profile in fixture['profiles']:
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
    u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,0x20000)
    binary=Path(profile['path']);elf=binary.with_suffix('.elf')
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==profile['sha256']
    flat=out/(profile['variant']+'-elf.bin')
    subprocess.run([args.arm_toolchain_bin/'arm-none-eabi-objcopy','-O','binary',elf,flat],check=True)
    assert flat.read_bytes()==binary.read_bytes()
    ElfImage(elf).load(u);probe.load(u)
    machines.append((u,profile))
reads=[];writes=[];minimum_stack=SP;checks=0
def access(machine,kind,address,size,value,user):
    global minimum_stack
    if SP-4096<=address and address+size<=SP:
        minimum_stack=min(minimum_stack,address);return
    spans=writes if kind==17 else reads
    assert any(lo<=address and address+size<=hi for lo,hi in spans),(kind,hex(address),size)
for u,_ in machines:u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)

def call(machine,data,align,work_size,capacity):
    global reads,writes,checks
    u,profile=machine
    u.mem_write(A,b'\xA7'*528);u.mem_write(A+align,data)
    u.mem_write(B,b'\xA7'*2304);u.mem_write(C,b'\xA7'*608)
    job=struct.pack('<9I',profile['symbols']['prepare']['address'],profile['symbols']['emit']['address'],A+align,len(data),B+align,work_size,C+align,capacity,0)+bytes(24)
    u.mem_write(J,job)
    reads=[(0x08000000,0x08100000),(A+align,A+align+len(data)),(B+align,B+align+work_size),(C+align,C+align+capacity),(J,J+60)]
    writes=[(B+align,B+align+work_size),(C+align,C+align+capacity),(J+32,J+60)]
    saved={r:(0xAC611337+r*0x1021)&0xFFFFFFFF for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    for reg,value in saved.items():u.reg_write(reg,value)
    u.reg_write(UC_ARM_REG_SP,SP);u.reg_write(UC_ARM_REG_LR,STOP|1);u.reg_write(UC_ARM_REG_R0,J);u.reg_write(UC_ARM_REG_XPSR,0x01000000)
    u.emu_start(probe.symbols['flash_probe']|1,STOP,count=100000000)
    assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_SP)==SP
    assert all(u.reg_read(reg)==value for reg,value in saved.items())
    assert bytes(u.mem_read(A+align,len(data)))==data
    assert bytes(u.mem_read(B,align))==b'\xA7'*align
    assert bytes(u.mem_read(B+align+work_size,2304-align-work_size))==b'\xA7'*(2304-align-work_size)
    assert bytes(u.mem_read(C,align))==b'\xA7'*align
    actual=bytes(u.mem_read(J,60));written=struct.unpack_from('<I',actual,32)[0]
    assert written<=capacity
    assert bytes(u.mem_read(C+align+written,608-align-written))==b'\xA7'*(608-align-written)
    checks+=1
    return u.reg_read(UC_ARM_REG_R0),written,bytes(u.mem_read(C+align,written)),actual[36:]

rng=random.Random(0xC061F411)
for n in (0,1,4,16,64,128,256,512):
    for pattern in range(6):
        data=bytes((65 if pattern==0 else 97+i%2 if pattern==1 else 97+i%3 if pattern==2 else rng.randrange(256) if pattern==3 else source[i%len(source)] if pattern==4 else image[i%len(image)]) for i in range(n))
        for align in range(4):
            for greedy in (False,True):
                size=3*n+64 if greedy else 4*(n+1)+64
                left=call(machines[0],data,align,size,576);right=call(machines[1],data,align,size,576)
                assert left==right,(n,pattern,align,greedy)
    print('Native Flash ELF',n,'bytes PASS',flush=True)
for capacity in (0,1,16):
    data=source[:128]
    left=call(machines[0],data,1,580,capacity);right=call(machines[1],data,1,580,capacity)
    assert left==right and not left[0]
result=dict(status='PASS',actual_resident_ELF_calls=checks,maximum_stack_access_bytes=SP-minimum_stack,
    identical_streams_and_prepared_plans=True,read_write_bounds=True,SP_and_callee_saved_registers=True,
    scope='Actual control/candidate Flash ELF prepare+emit calls in Cortex-M4 ISA; no device cycle claim.',
    manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
    probe_source_sha256=hashlib.sha256((ROOT/'tests/experimental/zx0_flash_arm_probe.cpp').read_bytes()).hexdigest())
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
print(result,flush=True)
