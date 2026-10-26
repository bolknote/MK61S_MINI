#!/usr/bin/env python3
"""Real SDK APP packing/relocation/entry tests for comparison candidates.

The normal builder and SDK are used. The research adapter only appends explicit
candidate -D flags to compiler invocations; actual commands are saved. Device
API query/capabilities are modeled, while APP startup, runtime binding, slot-19
tails, libc and candidate bodies execute as ARM. No device access or timing.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools'),str(ROOT/'tools/.mk61-app')]
from check_stm32_vectors import ElfImage
from string_compare_arm_self_test import pin,command,EXPERIMENT

def build(tc,out):
    out.mkdir(parents=True,exist_ok=False);logs=[];apps=[];native=[]
    spec=importlib.util.spec_from_file_location('comparison_app_builder',ROOT/'tools/build_portable_app.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    normal_run=builder.run
    for arch,target,limit in [('m4','stm32',6),('m0','picocalc-pico-h',4)]:
      for route,variants in [('standalone',range(limit+1)),('shared-local',range(limit+1)),('shared-bridge',[0])]:
       for variant in variants:
        folder=out/f'{arch}-{route}-v{variant}';name='SCHECK'
        defines=[f'-DMK61_STRCMP_VARIANT={variant}',f'-DMK61_STRNCMP_VARIANT={variant}']
        if route=='shared-bridge':defines+=['-DMK61_APP_STRCMP_USE_STRNCMP_RUNTIME=1']
        actual=[]
        def run(argv):
            argv=[str(EXPERIMENT/'sdk/portable/memory.c') if str(x)==str(ROOT/'sdk/portable/memory.c') else str(x) for x in argv]
            if Path(argv[0]).name in ['arm-none-eabi-gcc','arm-none-eabi-g++'] and '-c' in argv:argv[1:1]=['-I'+str(EXPERIMENT/'code')];argv+=defines
            actual.append(argv)
            return normal_run(argv)
        builder.run=run
        # The current standalone SDK has no strncmp body and ordinary APPs
        # do not link libc implicitly. Explicit newlib is the v0 baseline.
        libraries=[Path('-lc')] if route=='standalone' and variant==0 else []
        args=argparse.Namespace(target=target,name=name,source=[ROOT/'research/strcmp-strncmp-2026-10-26/APP-CHECK.c'],system=None,shared_runtime=route!='standalone',text_only=False,no_ui_fonts=False,local_float_math=False,local_float_math_mask=None,language_vm_compiler=False,split_language_vm=False,include=[],library=libraries,output_dir=folder,arm_toolchain_bin=tc,packer=ROOT/'tools/.mk61-app/mk61_module_pack.py',rustc=None,handled_magic=None)
        text=io.StringIO()
        with contextlib.redirect_stdout(text):report=builder.build(args)
        (folder/'build.log').write_text(text.getvalue())
        (folder/'actual-commands.json').write_text(json.dumps(actual,indent=2)+'\n')
        elf=ElfImage(folder/(name+'.elf'))
        assert report['memory_bytes']<=20480
        assert 'strcmp' in elf.symbols and 'strncmp' in elf.symbols
        apps.append(dict(arch=arch,route=route,variant=variant,APP=pin(folder/(name+'.APP')),ELF=pin(folder/(name+'.elf')),report=report,actual_commands=pin(folder/'actual-commands.json'),comparison_sizes={s:elf.sizes[s] for s in ['strcmp','strncmp']}))
        print(arch,route,variant,report['app_bytes'],'APP bytes',report['memory_bytes'],'RAM bytes',flush=True)
      flags=['-mcpu=cortex-m4','-mthumb','-mfloat-abi=hard','-mfpu=fpv4-sp-d16'] if arch=='m4' else ['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft']
      flags+=['-Os','-fno-builtin','-fno-tree-loop-distribute-patterns','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-I'+str(EXPERIMENT/'code'),'-I'+str(ROOT/'code')]
      source=EXPERIMENT/('code/system_strings.c' if arch=='m4' else 'ports/picocalc/memory.c')
      for variant in range(limit+1):
       for placement,address in [('flash',0x08002000 if arch=='m4' else 0x10002000),('sram',0x20002000)]:
        path=out/f'{arch}-native-{placement}-v{variant}.elf'
        defines=[f'-DMK61_STRCMP_VARIANT={variant}',f'-DMK61_STRNCMP_VARIANT={variant}','-DMK61_STRING_TEST_BUILD=1' if arch=='m4' else '-DPICO_ON_DEVICE=1']
        command([tc/'arm-none-eabi-gcc',*flags,*defines,'-nostdlib','-Wl,--gc-sections,--build-id=none',f'-Wl,-Ttext={hex(address)}','-Wl,-e,strcmp','-Wl,-u,strncmp',source,'-lc','-lgcc','-o',path],logs)
        elf=ElfImage(path)
        native.append(dict(arch=arch,variant=variant,placement=placement,ELF=pin(path),comparison_sizes={s:elf.sizes[s] for s in ['strcmp','strncmp']},full_firmware_link=False))
    builder.run=normal_run
    result=dict(apps=apps,native=native,commands=logs,physical_IO=0,default_variants=[0,0],runtime_count=26,runtime_strncmp_slot=19)
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def execute(build,core,out):
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE
    from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0,UC_CPU_ARM_CORTEX_M4,
        UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
        UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
        UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,
        UC_ARM_REG_XPSR,UC_ARM_REG_PRIMASK,UC_ARM_REG_CONTROL)
    saved_regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
    results=[];native_results=[];decode_logs=[];readers={}
    for arch in ['m4','m0']:
        reader=out/f'decode-app-{arch}'
        command(['c++','-std=c++17','-O2',*(['-DMK61_CORE_STANDALONE=1'] if arch=='m0' else []),'-I'+str(EXPERIMENT/'code'),'-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader],decode_logs)
        readers[arch]=pin(reader)
    for app in build['apps']:
      arch=app['arch'];flash=0x08000000 if arch=='m4' else 0x10000000
      resident=ElfImage(core/f'{arch}-flash.elf');elf=ElfImage(Path(app['ELF']['path']))
      packed=Path(app['APP']['path']).read_bytes();image_bytes,memory_bytes,entry=struct.unpack_from('<III',packed,28);crc=struct.unpack_from('<I',packed,52)[0]
      original_base=app['report']['load_address'];checked=0;runs=0;forwards=0;inits=0;negative=0
      for base in [0x20002000,0x20006000,0x2000a000]:
        decoded=out/f"{arch}-{app['route']}-v{app['variant']}-{base:x}.decoded"
        command([readers[arch]['path'],app['APP']['path'],decoded,hex(base)],decode_logs)
        blob=decoded.read_bytes();assert len(blob)==memory_bytes
        u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if arch=='m4' else UC_CPU_ARM_CORTEX_M0)
        u.mem_map(flash,0x100000);u.mem_map(0x20000000,0x20000);resident.load(u);u.mem_write(base,blob)
        stop=flash+0xff000;api=flash+0xf1000;services=flash+0xf2000;table=flash+0xf2100;query=flash+0xf2200;caps=flash+0xf2210;wrong=flash+0xf2220;sp=0x2001fff0
        def stub(address,value):u.mem_write(address,struct.pack('<HHI',0x4800,0x4770,value))
        stub(query,services);stub(caps,256);stub(wrong,0)
        # Only service discovery/capabilities are modeled. Any unsupported
        # function would branch to stop before normal return and fail below.
        u.mem_write(api,struct.pack('<IHHI',0x31505041,1,108,0)+struct.pack('<24I',*([stop|1]*23+[query|1])))
        u.mem_write(services,struct.pack('<IHH5I',0x31535953,2,28,0,caps|1,0,0,table))
        entrypoint=base+entry;queries=[];target_calls=[0]
        def query_hook(uc,address,size,user):
            del address,size,user
            queries.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
            assert queries[-1]==(1,2)
        u.hook_add(UC_HOOK_CODE,query_hook,begin=query,end=query)
        def target_hook(uc,address,size,user):
            del uc,address,size,user
            target_calls[0]+=1
        for name in ['old_native','byte1','byte4','word1','word2']+(['dsp1','dsp2'] if arch=='m4' else []):
            addr=resident.symbols[name+'_strncmp']&~1;u.hook_add(UC_HOOK_CODE,target_hook,begin=addr,end=addr)
        def bind(name):
            values=[stop|1]*26;values[19]=resident.symbols[name+'_strncmp']|1
            u.mem_write(table,struct.pack('<26I',*values))
        def invoke(command_id):
            saved={r:0xa1620000+i*0x1011 for i,r in enumerate(saved_regs)}
            for r,v in saved.items():u.reg_write(r,v)
            for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],[command_id,api,crc,4]):u.reg_write(r,v)
            u.mem_write(sp,bytes(4))
            for r,v in [(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000),(UC_ARM_REG_PRIMASK,0),(UC_ARM_REG_CONTROL,0)]:u.reg_write(r,v)
            u.emu_start(entrypoint|1,stop,count=100000000)
            assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==sp and all(u.reg_read(r)==v for r,v in saved.items()),('entry/AAPCS',app,base)
            return u.reg_read(UC_ARM_REG_R0)
        bind('old_native')
        if app['route']!='standalone':
            u.mem_write(table+19*4,bytes(4));assert invoke(0)==5;negative+=1;bind('old_native')
        assert invoke(0)==0;inits+=1
        backends=['old_native']
        if app['route']=='shared-bridge' and base==0x20006000:backends+=['byte1','byte4','word1','word2']+(['dsp1','dsp2'] if arch=='m4' else [])
        for backend in backends:
            bind(backend);before=target_calls[0]
            assert invoke(1)==0,('APP smoke',app,base,backend)
            count=struct.unpack('<I',u.mem_read(base+elf.symbols['checks']-original_base,4))[0]
            assert count==9520,(app,count)
            expected=0 if app['route']=='standalone' else 8160 if app['route']=='shared-local' else 9520
            assert target_calls[0]-before==expected,('runtime folding/routing',app,base,backend,target_calls[0]-before)
            forwards+=expected;checked+=count;runs+=1
        # Cached APP re-entry without reloading or rebinding initialization.
        before=target_calls[0];assert invoke(1)==0
        checked+=9520;runs+=1;forwards+=target_calls[0]-before
        if app['route']=='shared-bridge':
            u.mem_write(table+19*4,struct.pack('<I',wrong|1));assert invoke(1) in [10,11];negative+=1
        assert bytes(u.mem_read(base,image_bytes))==blob[:image_bytes],'APP code/data image mutated'
        if app['route']=='standalone':assert not queries
      row={k:app[k] for k in ['arch','route','variant','comparison_sizes']}
      row.update(APP=app['APP'],ELF=app['ELF'],load_addresses=[0x20002000,0x20006000,0x2000a000],successful_initializations=inits,successful_runs=runs,comparison_checks=checked,actual_runtime19_calls=forwards,negative_checks=negative,cached_reentry=True)
      results.append(row);print(arch,app['route'],app['variant'],checked,'packed APP checks PASS',flush=True)
    # Compile/link proof for opt-in resident entry points, including M0's
    # actual ports/picocalc/memory.c. These are not complete firmware builds.
    for item in build['native']:
        elf=ElfImage(Path(item['ELF']['path']));arch=item['arch'];flash=0x08000000 if arch=='m4' else 0x10000000
        u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if arch=='m4' else UC_CPU_ARM_CORTEX_M0)
        u.mem_map(flash,0x100000);u.mem_map(0x20000000,0x20000);elf.load(u)
        stop=flash+0xff000;sp=0x2001fff0;calls=0
        for length in [0,1,3,4,7,8,31,128,255]:
          a=b'\xff'*length
          for b in [a,b'\xff'*max(0,length-1),b'\x7f'+a[1:] if length else b'']:
           for aa,ba in [(0,0),(1,1),(0,1),(1,0)]:
            ap=0x20010000+aa;bp=flash+0x64000+ba;u.mem_write(ap,a+b'\0'+bytes(8));u.mem_write(bp,b+b'\0'+bytes(8))
            for name,n in [('strcmp',None),('strncmp',0),('strncmp',max(0,length-1)),('strncmp',length+1),('strncmp',0xffffffff)]:
                saved={r:0xabcd0000+i for i,r in enumerate(saved_regs)}
                for r,v in saved.items():u.reg_write(r,v)
                for r,v in [(UC_ARM_REG_R0,ap),(UC_ARM_REG_R1,bp),(UC_ARM_REG_R2,n or 0),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)]:u.reg_write(r,v)
                u.emu_start(elf.symbols[name]|1,stop,count=100000)
                assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==sp and all(u.reg_read(r)==v for r,v in saved.items()),('native ABI',item,name)
                value=u.reg_read(UC_ARM_REG_R0);value=value-(1<<32) if value>>31 else value
                left=a if n is None else a[:n];right=b if n is None else b[:n]
                assert (value>0)-(value<0)==(left>right)-(left<right),('native result',item,name,length,n)
                calls+=1
        native_results.append(dict(**item,successful_calls=calls))
    result=dict(status='PASS_PACKED_APPS_RELOCATION_RUNTIME_BINDING_AND_RESIDENT_ENTRIES_HOST_ONLY',physical_IO=0,hardware_winner=None,API_query_and_capabilities='modeled fixture only; real SDK binding/tails and ARM comparison bodies executed',production_format_decoders=readers,apps=results,native=native_results,total_APP_comparison_checks=sum(r['comparison_checks'] for r in results),total_resident_entry_calls=sum(r['successful_calls'] for r in native_results))
    (out/'decode-commands.json').write_text(json.dumps(decode_logs,indent=2)+'\n')
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--core-dir',type=Path,required=True)
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--run-existing',action='store_true')
    a=p.parse_args()
    products=json.loads((a.output_dir/'build.json').read_text()) if a.run_existing else build(a.toolchain_bin,a.output_dir)
    if not a.build_only:execute(products,a.core_dir,a.output_dir)
if __name__=='__main__':main()
