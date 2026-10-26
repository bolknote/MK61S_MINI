#!/usr/bin/env python3
"""Build and execute real M4/Thumb-1 comparison candidates and SDK runtime tails.

Unicorn verifies results, memory envelopes and AAPCS, not MCU timing. No USB,
serial, device discovery, firmware upload or reset is used by this program.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'research/strcmp-strncmp-2026-10-26/fixture-root'
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage

VARIANTS = ['byte1', 'byte4', 'word1', 'word2', 'dsp1', 'dsp2']
SOURCE = r'''
#include "string_compare_arm.h"
#define FN __attribute__((noipa,aligned(4)))
FN int old_native_strcmp(const char* a,const char* b) {
  while((unsigned char)*a==(unsigned char)*b && *a){++a;++b;}
  return (int)(unsigned char)*a-(int)(unsigned char)*b;
}
FN int old_sdk_strcmp(const char* left,const char* right) {
  const unsigned char *a=(const unsigned char*)left,*b=(const unsigned char*)right;
  while(*a && *a==*b){++a;++b;}return (int)*a-(int)*b;
}
FN int old_native_strncmp(const char* a,const char* b,size_t n) {
  while(n--){const unsigned x=(unsigned char)*a++,y=(unsigned char)*b++;
    if(x!=y)return (int)x-(int)y;if(!x)break;}return 0;
}
#define PAIR(name,v) \
FN int name##_strcmp(const char* a,const char* b){return mk61_sc_compare(a,b,0,0,v);} \
FN int name##_strncmp(const char* a,const char* b,size_t n){return mk61_sc_compare(a,b,n,1,v);}
PAIR(byte1,1) PAIR(byte4,2) PAIR(word1,3) PAIR(word2,4)
#if defined(__ARM_ARCH_7EM__)
PAIR(dsp1,5) PAIR(dsp2,6)
#endif
'''
BRIDGE = r'''
#include <stddef.h>
#include <stdint.h>
uintptr_t* mk61_app_runtime;
__attribute__((noipa)) int table_strncmp(const char* a,const char* b,size_t n) {
  return ((int(*)(const char*,const char*,size_t))mk61_app_runtime[19])(a,b,n);
}
'''

def pin(path):
    blob=path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())

def command(argv, log):
    p=subprocess.run([str(x) for x in argv],capture_output=True,text=True)
    log.append(dict(argv=[str(x) for x in argv],exit=p.returncode,stdout=p.stdout,stderr=p.stderr))
    if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    return p.stdout

def build(tc,out):
    out.mkdir(parents=True,exist_ok=False)
    (out/'candidates.c').write_text(SOURCE)
    (out/'bridge.c').write_text(BRIDGE)
    logs=[]; products=[]
    for arch in ['m4','m0']:
        flags=['-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft'] if arch=='m4' else ['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft']
        flags+=['-Os','-fno-builtin','-fno-ipa-icf','-fno-tree-loop-distribute-patterns','-ffunction-sections','-fdata-sections','-I'+str(EXPERIMENT/'code'),'-I'+str(ROOT/'code'),'-I'+str(ROOT/'sdk/portable/include')]
        flash=0x08000000 if arch=='m4' else 0x10000000
        for placement,address in [('flash',flash+0x2000),('sram',0x20002000)]:
            target=out/f'{arch}-{placement}.elf'
            command([tc/'arm-none-eabi-gcc',*flags,'-nostdlib','-Wl,--build-id=none',f'-Wl,-Ttext={hex(address)}','-Wl,-e,old_native_strcmp','-Wl,-u,strcmp','-Wl,-u,strncmp',out/'candidates.c','-lc','-lgcc','-o',target],logs)
            (out/f'{arch}-{placement}.dis').write_text(command([tc/'arm-none-eabi-objdump','-d',target],logs))
            products.append(dict(arch=arch,placement=placement,elf=pin(target)))
        # Actual SDK bridge body and actual runtime.S slot ordering. Other
        # services are section-GC'd; the real slot-19 tail remains unchanged.
        objs=[]
        for name,source in [('sdk',EXPERIMENT/'sdk/portable/memory.c'),('tails',ROOT/'sdk/portable/system/runtime.S'),('table',out/'bridge.c')]:
            obj=out/f'{arch}-{name}.o';objs.append(obj)
            command([tc/'arm-none-eabi-gcc',*flags,'-DMK61_APP_SHARED_RUNTIME=1','-DMK61_APP_STRCMP_USE_STRNCMP_RUNTIME=1','-DMK61_RUNTIME_POINTER=mk61_app_runtime','-c',source,'-o',obj],logs)
        target=out/f'{arch}-runtime.elf'
        command([tc/'arm-none-eabi-gcc',*flags,'-nostdlib','-Wl,--build-id=none,--gc-sections','-Wl,-Ttext=0x20006000','-Wl,--section-start=.bss=0x20007000','-Wl,-e,strcmp','-Wl,-u,strncmp','-Wl,-u,table_strncmp',*objs,'-o',target],logs)
        (out/f'{arch}-runtime.dis').write_text(command([tc/'arm-none-eabi-objdump','-d',target],logs))
        products.append(dict(arch=arch,placement='runtime',elf=pin(target)))
    (out/'build.json').write_text(json.dumps(dict(products=products,commands=logs,physical_IO=0),indent=2)+'\n')
    return products

def corpus(random_cases):
    rng=random.Random(0x5354434d)
    lengths=[*range(10),15,16,17,31,32,33,63,64,65,127,128,129,255,256,511]
    index=0
    for length in lengths:
      for aa in range(4):
       for ba in range(4):
        for mode in range(8):
          a=bytes(rng.randrange(1,256) for _ in range(length));b=a
          if mode in (1,2,3,6) and length:
              at={1:0,2:length//2,3:length-1,6:length//2}[mode]
              x=bytearray(a);y=bytearray(b)
              if mode==6:x[at]=0xff;y[at]=0x7f
              else:y[at]=1 if x[at]!=1 else 0xff
              a=bytes(x);b=bytes(y)
          elif mode==4:b=a[:length//2]
          elif mode==5:a=a[:length//2]
          elif mode==7:a=a[:length//2];b=a
          n=[0,1,max(0,length-1),length,length+1,length+3,65535,0xffffffff][(index+length+aa+ba//2)%8]
          yield dict(a=a,b=b,n=n,aa=aa,ba=ba,edge=index%2,alias=False,unterminated=False)
          index+=1
    for i in range(random_cases):
        a=bytes(rng.randrange(1,256) for _ in range(rng.randrange(520)))
        b=a if i%3==0 else bytes(rng.randrange(1,256) for _ in range(rng.randrange(520)))
        yield dict(a=a,b=b,n=rng.randrange(524),aa=rng.randrange(4),ba=rng.randrange(4),edge=i%2,alias=i%29==0,unterminated=False)
    # Bounded buffers need no terminator. A word load must never cross n.
    for n in range(65):
      for aa in range(4):
       for ba in range(4):
        yield dict(a=b'\xff'*n,b=b'\xff'*n,n=n,aa=aa,ba=ba,edge=1,alias=False,unterminated=True)

def run(products,out,random_cases):
    import struct
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
    from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0,UC_CPU_ARM_CORTEX_M4,
        UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
        UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
        UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,
        UC_ARM_REG_XPSR,UC_ARM_REG_PRIMASK,UC_ARM_REG_CONTROL)
    saved_regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
    cases=list(corpus(random_cases));results=[]
    for arch in ['m4','m0']:
      flash=0x08000000 if arch=='m4' else 0x10000000
      native=ElfImage(Path(next(x['elf']['path'] for x in products if x['arch']==arch and x['placement']=='flash')))
      for placement in ['flash','sram','runtime']:
        product=next(x for x in products if x['arch']==arch and x['placement']==placement)
        elf=ElfImage(Path(product['elf']['path']))
        u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if arch=='m4' else UC_CPU_ARM_CORTEX_M0)
        u.mem_map(flash,0x100000);u.mem_map(0x20000000,0x20000)
        elf.load(u)
        images=[elf]
        if placement=='runtime':native.load(u);images.append(native)
        code=[]
        for image in images:
          for kind,offset,vaddr,paddr,n,mem,flags,alignment in image.segments:
            if kind==1 and n and flags&1:code.append((vaddr,vaddr+n))
        stop=flash+0xff000;sp=0x2001fff0
        active={};counts={};max_frame=0;forwarded=[]
        def read(uc,access,address,n,value,user):
            nonlocal max_frame
            del uc,access,value,user
            if any(lo<=address and address+n<=hi for lo,hi in code):return
            if sp-64<=address and address+n<=sp:max_frame=max(max_frame,sp-address);return
            if placement=='runtime' and ((0x2001d000<=address and address+n<=0x2001d068) or (elf.symbols['mk61_app_runtime']<=address and address+n<=elf.symbols['mk61_app_runtime']+4)):return
            assert any(lo<=address and address+n<=hi for lo,hi in active['ranges']),('read bound',arch,placement,active,hex(address),n)
            if active['group']==4 and n>=4:assert address%4==0,('unaligned word',hex(address),n)
        def write(uc,access,address,n,value,user):
            nonlocal max_frame
            del uc,access,value,user
            assert sp-64<=address and address+n<=sp,('input/non-frame write',arch,placement,hex(address),n)
            max_frame=max(max_frame,sp-address)
        u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
        if placement=='runtime':
            u.mem_write(elf.symbols['mk61_app_runtime'],struct.pack('<I',0x2001d000))
            def target_entry(uc,address,size,user):
                del address,size,user
                forwarded.append(tuple(uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]))
            for variant in ['old_native',*VARIANTS[:6 if arch=='m4' else 4]]:
                at=native.symbols[variant+'_strncmp']&~1
                u.hook_add(UC_HOOK_CODE,target_entry,begin=at,end=at)
        def call(name,args,target=None):
            if target:
                u.mem_write(0x2001d000,struct.pack('<26I',*([stop|1]*19+[native.symbols[target]|1]+[stop|1]*6)))
            expected_saved={r:0xa1710000+i*0x1023 for i,r in enumerate(saved_regs)}
            for r,v in expected_saved.items():u.reg_write(r,v)
            for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],(*args,0,0,0,0)):u.reg_write(r,v)
            mask=(sum(counts.values())&1)
            for r,v in [(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000),(UC_ARM_REG_PRIMASK,mask),(UC_ARM_REG_CONTROL,0)]:u.reg_write(r,v)
            before=len(forwarded)
            u.emu_start(elf.symbols[name]|1,stop,count=100000)
            assert u.reg_read(UC_ARM_REG_PC)==stop,('no return',name)
            assert u.reg_read(UC_ARM_REG_SP)==sp and all(u.reg_read(r)==v for r,v in expected_saved.items()),('AAPCS',arch,placement,name)
            assert u.reg_read(UC_ARM_REG_PRIMASK)==mask and u.reg_read(UC_ARM_REG_CONTROL)==0,('control registers',name)
            if target:
                assert len(forwarded)==before+1,('wrong runtime target/number',name)
                assert forwarded[-1]==(args[0],args[1],0xffffffff if name=='strcmp' else args[2]),('wrong runtime arguments',name)
            value=u.reg_read(UC_ARM_REG_R0);value=value-(1<<32) if value&0x80000000 else value
            counts[name if not target else name+'->'+target]=counts.get(name if not target else name+'->'+target,0)+1
            return (value>0)-(value<0)
        variants=['old_native',*VARIANTS[:6 if arch=='m4' else 4]]
        for i,c in enumerate(cases):
            a=c['a'];b=a if c['alias'] else c['b'];n=c['n']
            # Alternate RAM/RAM, RAM/Flash and Flash/Flash; every alignment is
            # tested at both leading and trailing page edges across the corpus.
            apage=0x20008000 if i%3!=2 else flash+0x60000
            bpage=0x2000a000 if i%3==0 else flash+0x64000
            def place(page,blob,align):
                extent=len(blob)+(not c['unterminated'])
                pointer=page+align if not c['edge'] else page+4096-extent-((4096-extent-align)&3)
                data=bytearray(b'\xa5'*4096);at=pointer-page;data[at:at+len(blob)]=blob
                if not c['unterminated']:data[at+len(blob)]=0
                u.mem_write(page,bytes(data))
                return pointer,bytes(data)
            ap,apdata=place(apage,a,c['aa']);bp,bpdata=place(bpage,b,c['ba'])
            if c['alias']:bp=ap
            for bounded in [False,True]:
                if not bounded and c['unterminated']:continue
                oracle=(a[:n]>b[:n])-(a[:n]<b[:n]) if bounded else (a>b)-(a<b)
                if placement=='runtime':
                    routes=[('strncmp' if bounded else 'strcmp',v+'_strncmp',4 if v in ['word1','word2','dsp1','dsp2'] else 1) for v in variants]
                    if bounded:routes += [('table_strncmp',v+'_strncmp',4 if v in ['word1','word2','dsp1','dsp2'] else 1) for v in variants]
                else:
                    suffix='_strncmp' if bounded else '_strcmp'
                    names=[v+suffix for v in variants]+([] if bounded else ['old_sdk_strcmp'])+['strncmp' if bounded else 'strcmp']
                    routes=[(name,None,8 if name=='strcmp' else 4 if name=='strncmp' or name.startswith(('word','dsp')) else 1) for name in names]
                for name,target,group in routes:
                    ranges=[]
                    for p,blob in [(ap,a),(bp,b)]:
                        end=p+len(blob) if c['unterminated'] else ((p+len(blob)+group)&~(group-1))
                        if bounded:end=min(end,p+n)
                        # Newlib's ARM strcmp aligns a source down to eight
                        # bytes before LDRD. Record that baseline separately; our
                        # candidates must never read before the input pointer.
                        start=(p&~7) if name=='strcmp' and placement!='runtime' else p
                        ranges.append((start,end))
                    active.update(ranges=ranges,group=group,name=name,target=target,case=i,bounded=bounded)
                    assert call(name,(ap,bp,n) if bounded else (ap,bp),target)==oracle,('result',arch,placement,name,target,i,c)
            assert bytes(u.mem_read(apage,4096))==apdata and bytes(u.mem_read(bpage,4096))==bpdata,'input changed'
        # n==0 must not touch even unmapped input pointers.
        active.update(ranges=[],group=1)
        zero_names=['strncmp','table_strncmp'] if placement=='runtime' else [v+'_strncmp' for v in variants]+['strncmp']
        for name in zero_names:
            target='word2_strncmp' if placement=='runtime' else None
            assert call(name,(0xe0000000,0xfffff000,0),target)==0
        row=dict(arch=arch,placement=placement,elf=product['elf'],cases=len(cases),calls=counts,total_calls=sum(counts.values()),maximum_stack_bytes=max_frame,exact_slot19_forwarding_checks=len(forwarded),callee_saved_SP_PRIMASK_CONTROL=True,inputs_unchanged=True)
        results.append(row)
        print(arch,placement,row['total_calls'],'calls PASS',flush=True)
    result=dict(status='PASS_HOST_ARM_CORRECTNESS_NOT_HARDWARE_TIMING',physical_IO=0,hardware_winner=None,candidate_word_envelope='aligned 4-byte containing NUL word; no reads before input or beyond n',newlib_baseline_envelope='strcmp: align down to 8-byte group, up to 7 prefix/tail bytes; strncmp: 4-byte NUL group, no prefix or beyond-n reads',results=results)
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--random-cases',type=int,default=512)
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--run-existing',action='store_true')
    a=p.parse_args()
    products=json.loads((a.output_dir/'build.json').read_text())['products'] if a.run_existing else build(a.toolchain_bin,a.output_dir)
    if not a.build_only:run(products,a.output_dir,a.random_cases)
if __name__=='__main__':main()
