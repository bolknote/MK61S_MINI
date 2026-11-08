#!/usr/bin/env python3
"""Build the separately downloadable AY/TurboSound Cortex-M3 sound module."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[3]
RUNTIME=ROOT/'sdk/coproc'
sys.path[:0]=[str(ROOT),str(RUNTIME)]
from elf32 import ELF
from tools.firmware.picocalc.build_picocalc import compiler_bin


def build(output,toolchain=None,optimization='-Os',fast_init=0,slice_samples=16,step_budget_us=0,init_budget_us=100,lto=False,silent_batch=False):
    if not 1<=slice_samples<=40:raise ValueError('M3 slice must be 1..40 samples')
    if not 0<=step_budget_us<=1250 or (step_budget_us>1000 and slice_samples>16):
        raise ValueError('M3 STEP budget must be 0..1250 us; above 1000 us requires chunks <=16 samples')
    if not 1<=init_budget_us<=1250 or (init_budget_us>100 and slice_samples>16):
        raise ValueError('M3 INIT budget must be 1..1250 us; above 100 us requires chunks <=16 samples')
    toolchain=compiler_bin(toolchain)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    app=ROOT/'examples/portable-apps/SPECTRUM'
    sources=[app/'m3_audio_module.c',app/'m3_audio_memory.c',ROOT/'third_party/emu2149/emu2149.c']
    tool=lambda name:str(Path(toolchain)/('arm-none-eabi-'+name))
    flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11',optimization,'-g','-mword-relocations',
           '-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables',
           '-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections','-Wall','-Wextra',
           '-I'+str(RUNTIME)]
    if fast_init:flags+=['-DEMU2149_M3_AUDIO=1','-DSPECTRUM_M3_FAST_INIT='+str(fast_init)]
    flags+=['-DSPECTRUM_M3_SLICE_SAMPLES='+str(slice_samples)]
    flags+=['-DSPECTRUM_M3_STEP_BUDGET_US='+str(step_budget_us)]
    flags+=['-DSPECTRUM_M3_INIT_BUDGET_US='+str(init_budget_us)]
    if lto:flags+=['-flto']
    if silent_batch:flags+=['-DSPECTRUM_M3_SILENT_BATCH=1']
    elf=output/'AY.elf'
    command=[tool('gcc'),*flags,'-nostdlib',*map(str,sources),'-Wl,-T,'+str(RUNTIME/'module.ld'),
             '-Wl,--emit-relocs,--gc-sections,-Map='+str(output/'AY.map'),'-o',str(elf)]
    with (output/'build.log').open('w') as log:
        subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    binary=output/'AY.bin'
    subprocess.run([tool('objcopy'),'-O','binary','-j','.image',str(elf),str(binary)],check=True)
    e=ELF(elf);image=binary.read_bytes();memory=e.symbols['__memory_end']['value']-0x20000000
    bss=memory-len(image);relocs=[]
    for address,kind in e.relocations():
        if kind==2:relocs.append(address-0x20000000)
        elif kind not in (3,10,30,42):raise ValueError('Unsupported relocation '+str(kind))
    relocs=sorted(set(relocs))
    if memory>6144 or len(relocs)>64:raise ValueError('M3 sound module exceeds resident budget')
    for at in relocs:
        assert at%4==0 and at+4<=len(image)
        assert 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+memory
    for name,symbol in e.symbols.items():
        if symbol['index']==0:raise ValueError('Undefined module symbol '+name)
    payload=image+b''.join(struct.pack('<I',at)for at in relocs)
    words=[0x314d3353,1,64,64+len(payload),len(image),bss,e.entry-0x20000000,len(relocs),
           512,512,512,2000,zlib.crc32(payload),0,0x70301]
    header=struct.pack('<15I',*words);header+=struct.pack('<I',zlib.crc32(header))
    package=output/'AY.S3M';package.write_bytes(header+payload)
    inputs=[*sources,app/'m3_audio_protocol.h',RUNTIME/'stm3_module.h',RUNTIME/'module.ld',Path(__file__)]
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    result=dict(package=str(package),sha256=sha(package),image_bytes=len(image),bss_bytes=bss,
                memory_bytes=memory,memory_limit=6144,package_bytes=package.stat().st_size,
                relocations=relocs,entry_offset=e.entry-0x20000000,sample_rate=25000,
                maximum_samples_per_job=120,fast_init_samples=fast_init,slice_samples=slice_samples,
                step_budget_us=step_budget_us,init_budget_us=init_budget_us,optimization=optimization,lto=lto,silent_batch=silent_batch,
                output='mono signed16 PCM1 or exact final PWM8 PWM1, selected in CONFIG',
                synthesizer='shared emu2149 AY8910/TurboSound + beeper/Covox/SpecDrum + DC filter',
                source_sha256={str(p.relative_to(ROOT)):sha(p)for p in inputs},hardware_verified=False)
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir',type=Path,default=ROOT/'.build/spectrum-m3-audio-20261107/module')
    ap.add_argument('--arm-toolchain-bin',type=Path)
    ap.add_argument('--optimization',choices=['Os','O2','O3'],default='Os')
    ap.add_argument('--fast-init',type=int,choices=[0,64,80,96,120],default=0)
    ap.add_argument('--slice-samples',type=int,choices=[16,24,32,40],default=16)
    ap.add_argument('--step-budget-us',type=int,choices=[0,500,750,900,1000,1250],default=0)
    ap.add_argument('--init-budget-us',type=int,choices=[100,250,500,750,1000,1250],default=100)
    ap.add_argument('--lto',action='store_true',help='Optimize synthesis and the module together at link time')
    ap.add_argument('--silent-batch',action='store_true',help='Advance a silent event-free second PSG in sample groups')
    args=ap.parse_args();print(json.dumps(build(args.build_dir,args.arm_toolchain_bin,'-'+args.optimization,args.fast_init,args.slice_samples,args.step_budget_us,args.init_budget_us,args.lto,args.silent_batch),indent=2))
