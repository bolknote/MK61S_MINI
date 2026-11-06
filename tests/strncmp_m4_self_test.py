#!/usr/bin/env python3
"""Execute production strncmp, standalone libc and the real SDK slot19 tail.

The M4 body pin ties production to the measured Classic kernel. Other targets
keep their byte C function; their identical control body is checked separately.
No time in this test is an on-device performance result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from unicorn_runtime import Uc

MEASURED='25557c04ff36ffb12d0e376c167a57018d15fdada1e9afa2a6d17cc044534276'
NEWLIB='7eebcae0abcbf7c0f7d85c9966550f5c560a6477d19f355c6d3353727c27306d'


def body(e,name):
    p=e.symbols[name]&~1;n=e.sizes[name]
    return next(e.data[o+p-v:o+p-v+n] for k,o,v,pa,size,mem,flags,align in e.segments if k==1 and v<=p and p+n<=v+size)


def corpus():
    index=0
    for length in [0,1,2,3,4,7,8,15,16,17,31,32,63,64,127,128,255,512]:
        for aa in range(4):
            for ba in range(4):
                for mode in range(5):
                    a=bytes(1+i%251 for i in range(length));b=a
                    if length and mode in [1,2,4]:
                        a=bytearray(a);b=bytearray(b);at=0 if mode==1 else length-1
                        if mode==4:a[at]=255;b[at]=128
                        else:b[at]=254
                        a,b=bytes(a),bytes(b)
                    if length and mode==3:a=a[:length//2]
                    n=[0,1,max(0,length-1),length,length+1,length+3,0xffffffff][index%7]
                    yield a+b'\0',b+b'\0',n,aa,ba,index%4,index%2,index%19==0
                    index+=1
    for n in range(65):
        yield b'\xff'*n,b'\xff'*n,n,n%4,(n//4)%4,n%4,n%2,False


def oracle(a,b,n):
    for i in range(n):
        x,y=a[i],b[i]
        if x!=y or x==0:return x-y,i+1
    return 0,n


def execute(native,sdk,tail,baseline_m0):
    from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    import unicorn.arm_const as arm
    results=[];cases=list(corpus())
    for route,image,entry,word in [('native-m4',native,'strncmp',False),('standalone-sdk',sdk,'strncmp',True),
                                  ('runtime19',native,'strncmp',False),('native-m0',baseline_m0,'strncmp',False)]:
        u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M0 if route=='native-m0' else arm.UC_CPU_ARM_CORTEX_M4)
        u.mem_map(0x08000000,0x80000);u.mem_map(0x20000000,0x20000);image.load(u)
        images=[image];table=0x20008000
        if route=='runtime19':
            tail.load(u);images.append(tail);u.mem_write(tail.symbols['mk61_app_runtime'],struct.pack('<I',table))
            pointers=[0x0807ff01]*26;pointers[19]=image.symbols['strncmp']|1;u.mem_write(table,struct.pack('<26I',*pointers))
        code=[(v,v+size) for e in images for k,o,v,pa,size,mem,flags,align in e.segments if k==1 and size]
        sp=0x2001fff0;stop=0x0807ff00;active=[];maxframe=0;calls=0
        def read(uc,access,address,size,value,user):
            nonlocal maxframe
            if any(lo<=address and address+size<=hi for lo,hi in code):return
            if sp-256<=address and address+size<=sp:maxframe=max(maxframe,sp-address);return
            if route=='runtime19' and (table<=address and address+size<=table+104 or tail.symbols['mk61_app_runtime']<=address and address+size<=tail.symbols['mk61_app_runtime']+4):return
            assert any(lo<=address and address+size<=hi for lo,hi in active),(route,'read envelope',hex(address),size,active)
            if not word:assert size==1,(route,'scalar kernel must only read bytes')
        def write(uc,access,address,size,value,user):
            nonlocal maxframe
            assert sp-256<=address and address+size<=sp,(route,'non-frame write',hex(address),size)
            maxframe=max(maxframe,sp-address)
        u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
        regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(4,12)]
        def invoke(left,right,n):
            nonlocal calls
            saved={r:0xa1500000+i*257 for i,r in enumerate(regs)}
            for r,v in saved.items():u.reg_write(r,v)
            for r,v in [(arm.UC_ARM_REG_R0,left),(arm.UC_ARM_REG_R1,right),(arm.UC_ARM_REG_R2,n),
                        (arm.UC_ARM_REG_SP,sp),(arm.UC_ARM_REG_LR,stop|1),(arm.UC_ARM_REG_XPSR,0x01000000),
                        (arm.UC_ARM_REG_PRIMASK,calls%2),(arm.UC_ARM_REG_CONTROL,0)]:u.reg_write(r,v)
            address=tail.symbols['strncmp'] if route=='runtime19' else image.symbols[entry]
            u.emu_start(address|1,stop,count=100000)
            assert u.reg_read(arm.UC_ARM_REG_PC)==stop and u.reg_read(arm.UC_ARM_REG_SP)==sp
            assert all(u.reg_read(r)==v for r,v in saved.items()),(route,'callee-saved')
            assert u.reg_read(arm.UC_ARM_REG_PRIMASK)==calls%2 and u.reg_read(arm.UC_ARM_REG_CONTROL)==0
            calls+=1;value=u.reg_read(arm.UC_ARM_REG_R0);return value if value<0x80000000 else value-0x100000000
        for a,b,n,aa,ba,bank,edge,alias in cases:
            bases=[0x20010000 if not bank&2 else 0x08060000,0x20012000 if not bank&1 else 0x08062000]
            pointers=[]
            for base,raw,align in zip(bases,[a,b],[aa,ba]):
                p=base+128+align if not edge else base+4096-len(raw)-64
                if edge:p-=(p-align)&3
                u.mem_write(base,bytes([165])*4096);u.mem_write(p,raw);pointers.append(p)
            if alias and aa==ba and bank in [0,3]:pointers[1]=pointers[0];b=a
            wanted,consumed=oracle(a,b,n);active=[]
            for p in pointers:
                end=min(n,((p+consumed+3)&~3)-p) if word else consumed
                active.append((p,p+end))
            actual=invoke(*pointers,n);assert (actual>0)-(actual<0)==(wanted>0)-(wanted<0),(route,n,aa,ba,actual,wanted)
            if not word:assert actual==wanted,(route,'exact unsigned-byte difference')
        active=[];assert invoke(0x60000000,0x60001000,0)==0
        results.append(dict(route=route,calls=calls,max_frame=maxframe))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--toolchain-bin',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);commands=[]
    def run(args):
        args=list(map(str,args));r=subprocess.run(args,capture_output=True,text=True);commands.append(dict(argv=args,EXIT=r.returncode,stdout=r.stdout,stderr=r.stderr))
        (a.output/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,r.stdout+r.stderr
    def flags(cpu):return ['-mcpu='+cpu,'-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-fno-lto','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'code'),'-I'+str(ROOT/'sdk/portable/include')]
    cc=a.toolchain_bin/'arm-none-eabi-gcc';images={}
    for name,cpu,extra in [('m4','cortex-m4',[]),('f401','cortex-m4',['-DSTM32F401xC']),('m0','cortex-m0plus',[])]:
        path=a.output/(name+'.elf');run([cc,*flags(cpu),*extra,'-DMK61_STRING_TEST_BUILD=1','-nostdlib','-Wl,--gc-sections,--build-id=none,-e,strncmp,-Ttext=0x08002000',ROOT/'code/system_strings.c','-lgcc','-o',path]);images[name]=ElfImage(path)
    assert len(body(images['m4'],'strncmp'))==84 and hashlib.sha256(body(images['m4'],'strncmp')).hexdigest()==MEASURED
    assert len(body(images['f401'],'strncmp'))==42 and hashlib.sha256(body(images['f401'],'strncmp')).hexdigest()=='08730e4007562fd6d0503c38eb4da5df28acfb853952185d03b5df255a094750'
    control=a.output/'m0-control.c';control.write_text('#include <stddef.h>\n#pragma GCC optimize ("no-tree-loop-distribute-patterns")\nint strncmp(const char*a,const char*b,size_t n){while(n--){const unsigned char x=*a++,y=*b++;if(x!=y)return(int)x-(int)y;if(!x)break;}return 0;}\n')
    run([cc,*flags('cortex-m0plus'),'-nostdlib','-Wl,--gc-sections,--build-id=none,-e,strncmp,-Ttext=0x08002000',control,'-o',a.output/'m0-control.elf'])
    assert body(images['m0'],'strncmp')==body(ElfImage(a.output/'m0-control.elf'),'strncmp'),'M0 fallback changed'
    run([cc,*flags('cortex-m4'),'-nostdlib','-Wl,--gc-sections,--build-id=none,-e,strncmp,-Ttext=0x20002000',ROOT/'sdk/portable/memory.c','-lc','-lgcc','-o',a.output/'sdk.elf'])
    sdk=ElfImage(a.output/'sdk.elf');assert len(body(sdk,'strncmp'))==120 and hashlib.sha256(body(sdk,'strncmp')).hexdigest()==NEWLIB
    pointer=a.output/'pointer.c';pointer.write_text('#include <stdint.h>\nuintptr_t*mk61_app_runtime;\n')
    run([cc,*flags('cortex-m4'),'-DMK61_RUNTIME_POINTER=mk61_app_runtime','-nostdlib','-Wl,--gc-sections,--build-id=none,-e,strncmp,-Ttext=0x20006000,--section-start=.bss=0x20007000',ROOT/'sdk/portable/system/runtime.S',pointer,'-o',a.output/'tail.elf'])
    tail=ElfImage(a.output/'tail.elf');assert len(body(tail,'strncmp'))==12
    result=dict(status='PASS_PRODUCTION_M4_NATIVE_SDK_RUNTIME19_AND_UNCHANGED_F401_M0',physical_IO=0,results=execute(images['m4'],sdk,tail,images['m0']),
                native_M4_bytes=84,native_M4_SHA256=MEASURED,SDK_bytes=120,SDK_SHA256=NEWLIB,runtime26_slot=19,public_tail_bytes=12)
    (a.output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
