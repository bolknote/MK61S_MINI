#!/usr/bin/env python3
"""Real ARM frontends/index service/VM/INPUT with bounded Flash callbacks.

NOR and keyboard are fixtures. Every APP replacement poisons its predecessor;
no compiler/editor pointers or full-image SRAM allocations survive a call.
"""
import argparse
import bisect
import sys
import binascii
import json
import struct
import tempfile
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from run_language_vm_overlay_arm_tests import OverlayMachine, encode_number
from run_language_vm_arm_tests import package
from run_portable_system_arm_tests import Elf, ROOT, run

VERSION=13
STATE_SIZE=1992
STACK=976
PROMPT=1860
PROMPT_OFFSET=1852
PROMPT_LENGTH=1856
LANGUAGE=1956
INPUT_VALUE=1840
EXEC_SIZE=68
RESULT=36
MAX_SOURCE_WINDOW=3152-512-1024 # compiler prefix minus frontend and Writer payload

class FlashMachine(OverlayMachine):
    def __init__(self,resident,address_index=0):
        super().__init__(resident,False,address_index)
        self.current_request=None
        self.pages=[bytearray() for _ in range(4)]
        self.counts={"read":0,"write":0,"lookup":0}
        self.max_read=self.max_write=self.max_source_read=0
        self.call_instruction_limit=500_000_000
        self.call_timeout_us=180_000_000
        self.flash_callbacks={0x080F1000+i*4:name for i,name in enumerate(("read","write","truncate","poll","input","lookup"))}
        for address in self.flash_callbacks:self.uc.mem_write(address,b'\x70\x47')
        self.watched=set(self.callbacks)|set(self.basic_display)|set(self.flash_callbacks)|{self.syscall&~1,self.binary_stop}
    def hook(self,uc,address,size,ctx):
        # This suite checks wire/relocation/eviction correctness, not emulator
        # stack-watermark sampling. Avoid four Python register reads at every
        # arithmetic instruction; keep every actual service/display callback.
        if hasattr(self,'watched') and address not in self.watched and address!=getattr(self,'debug_capability_return',None) and not (self.float_return and address==self.float_return[0]):
            return
        if getattr(self,'current_request',None) and address==(self.syscall&~1):
            if self.uc.mem_read(self.current_request+16,1)!=b'\0':
                raise AssertionError(('compiler error before UI',bytes(self.uc.mem_read(self.current_request,52)).hex(),self.counts))
        name=getattr(self,'flash_callbacks',{}).get(address)
        if not name:return super().hook(uc,address,size,ctx)
        a,b,c,d=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        result=1
        if name in ("read","input"):
            space,at,out,n=(b,c,d,self.words(uc.reg_read(UC_ARM_REG_SP),1)[0]) if name=="read" else (2,b,c,d)
            self.max_read=max(self.max_read,n);self.counts['read']+=1
            if at+n>len(self.pages[space]):result=0
            else:uc.mem_write(out,bytes(self.pages[space][at:at+n]))
        elif name=="write":
            n=self.words(uc.reg_read(UC_ARM_REG_SP),1)[0]
            assert n==1024 and c%1024==0
            self.max_write=max(self.max_write,n);self.counts['write']+=1
            page=self.pages[b]
            if len(page)<c+n:page.extend(bytes(c+n-len(page)))
            page[c:c+n]=uc.mem_read(d,n)
            self.resource_revision+=1 # Source content stamp must survive this.
        elif name=="truncate":
            assert c==0;self.pages[b].clear();self.resource_revision+=1
        elif name=="lookup":
            self.counts['lookup']+=1
            count=struct.unpack_from('<H',self.pages[2],18)[0]
            rows=[struct.unpack_from('<II',self.pages[2],32+i*8) for i in range(count)]
            keys=[row[0 if c else 1] for row in rows]
            if c:
                i=bisect.bisect_left(keys,b);value=rows[i][1] if i<count and keys[i]==b else 0xFFFFFFFF
            else:
                i=bisect.bisect_right(keys,b);value=rows[i-1][0] if i else 0
            self.put(d,value)
        uc.reg_write(UC_ARM_REG_R0,result);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def system(self,op,a,b,c,p):
        if op==37 and a==6:
            if b not in self.files:return 0
            self.put(p,binascii.crc32(self.files[b][2]));return 1
        if op==37 and a==5:
            revision,inode,offset,out,n,mode=struct.unpack('<IHHIHH',self.uc.mem_read(p,16))
            if mode==2:
                if inode not in self.files or revision!=binascii.crc32(self.files[inode][2]):return 0
                data=self.files[inode][2][offset:offset+n]
                if len(data)!=n:return 0
                assert n<=MAX_SOURCE_WINDOW;self.max_source_read=max(self.max_source_read,n)
                self.uc.mem_write(out,data);return 1
        return super().system(op,a,b,c,p)
    def io(self,elf):
        address=self.input+16
        prepare=elf.symbol('Store2ioEvENUlPvS2_hE_4_FUN')|1
        stub=lambda name:next(a|1 for a,n in self.flash_callbacks.items() if n==name)
        self.put(address,0,stub('read'),stub('write'),stub('truncate'),stub('poll'),prepare,stub('lookup'))
        return address,stub('input')

def compile_program(machine,packages,elf,language):
    basic=language==1
    text='1 GOTO 30000\n' if basic else '1.0 G 9.0\n'
    for i in range(4400):
        text+=f'{i+2} A=1\n' if basic else f'{2+i//1000}.{i%1000} S A=1\n'
    text+=('30000 S=0;FOR I=1 TO 2;GOSUB 31000;NEXT I;ON 9 GOSUB '+','.join(['32000']*9)+'\n'
           '30010 ON 9 GOTO '+','.join(['32010']*9)+'\n31000 INPUT "value?",B;S=S+B;RETURN\n'
           '32000 S=S+1;RETURN\n32010 S=S-1;.RA=S;END\n'
           if basic else '9.0 S S=0;F I=1,2;D 10\n9.1 B (-1)9.2,99.99,99.99\n9.2 B (0)99.99,9.3,99.99\n9.3 B (1)99.99,99.99,9.4\n9.4 S .RA=S;E\n10.0 A "value?",B;S S=S+B;R\n')
    machine.files[42]=(3 if basic else 2,'VMTEST',text.encode())
    machine.partitioned=True;machine.load(packages['tinybasic' if basic else 'focal'])
    io,input_callback=machine.io(elf)
    request=machine.input+512;machine.uc.mem_write(request,bytes(52))
    machine.put(request,52,VERSION,0,0xFFFFFFFF);machine.put(request+48,io)
    machine.current_request=request
    try:result=machine.call(0x206 if basic else 0x106,42,1 if basic else 0,request)
    except Exception:
        print('ARM compile diagnostic',bytes(machine.uc.mem_read(request,52)).hex(),machine.counts,[len(p) for p in machine.pages],hex(machine.base),machine.trace[-10:],file=sys.stderr,flush=True)
        raise
    machine.current_request=None
    wire=bytes(machine.uc.mem_read(request,52))
    assert result==(1 if basic else 0) and wire[16]==0 and wire[36]==1, (result,wire.hex(),machine.trace[-10:])
    size=struct.unpack_from('<I',wire,20)[0]
    assert size>65536 and machine.pages[2][:4]==b'LBV2'
    assert 256<machine.max_source_read<=MAX_SOURCE_WINDOW
    return bytes(machine.pages[2][:size]),io,input_callback

def execute(machine,packages,image,io,input_callback,language):
    machine.pages[2]=bytearray(image)+bytearray((-len(image))%1024)
    execution,overlay,entry,temporary,main_metadata,expr_metadata=[machine.input+x for x in (640,720,768,832,920,960)]
    variables=machine.input+128;state=machine.workspace
    array=state+4176+424
    machine.uc.mem_write(variables,bytes(208));machine.uc.mem_write(array,bytes(512 if language==2 else 3080))
    machine.uc.mem_write(state,b'\xA5'*STATE_SIZE);machine.uc.mem_write(state+LANGUAGE,bytes((language,)))
    machine.uc.mem_write(execution,bytes(EXEC_SIZE));machine.put(execution,EXEC_SIZE,VERSION,0,len(image),variables,array,64 if language==2 else 385)
    machine.uc.mem_write(execution+28,b'\x01')
    machine.put(execution+52,0,input_callback,len(image),io)
    machine.put(overlay,24,VERSION,execution,state,main_metadata,0)
    machine.load(packages['language-input']);assert machine.call(0x705,overlay)==1
    assert machine.uc.mem_read(execution+RESULT,1)==b'\0'
    inputs=0
    while True:
        machine.load(packages['language-vm']);assert machine.call(0x700,overlay)==1
        error=machine.uc.mem_read(execution+RESULT,1)[0]
        if error!=15:
            assert error==0 and inputs==2,(error,inputs,machine.trace[-8:])
            assert machine.refs[4,10]==10,machine.refs
            return
        pc=machine.words(execution+RESULT+4,1)[0]
        assert pc>65536 and image[pc]==48
        offset=machine.words(state+PROMPT_OFFSET,1)[0]
        length=struct.unpack('<H',machine.uc.mem_read(state+PROMPT_LENGTH,2))[0]
        assert offset==pc+3 and length==6 and bytes(machine.uc.mem_read(state+PROMPT,6))==b'value?'
        expression=state+STACK+512
        machine.load(packages['language-input']);machine.input_keys('2+3')
        machine.uc.mem_write(entry,bytes(40));machine.put(entry,40,VERSION,state+PROMPT,expression)
        machine.uc.mem_write(entry+24,struct.pack('<HHHBB',6,256,0,language,0))
        assert machine.call(0x703,entry)==1 and machine.uc.mem_read(entry+31,1)==b'\x02'
        length=struct.unpack('<H',machine.uc.mem_read(entry+28,2))[0]
        machine.uc.mem_write(temporary,bytes(machine.uc.mem_read(execution,EXEC_SIZE)))
        machine.put(temporary+8,expression,length);machine.uc.mem_write(temporary+52,bytes(16))
        machine.put(overlay+8,temporary);machine.put(overlay+16,expr_metadata);machine.uc.mem_write(overlay+20,b'\x02')
        assert machine.call(0x705,overlay)==1 and machine.uc.mem_read(temporary+RESULT,1)==b'\0'
        control=bytes(machine.uc.mem_read(state,976))
        machine.load(packages['language-vm']);assert machine.call(0x700,overlay)==1
        assert machine.uc.mem_read(temporary+RESULT,1)==b'\0' and bytes(machine.uc.mem_read(state,976))==control
        assert bytes(machine.uc.mem_read(state+INPUT_VALUE,8))==encode_number(5)
        machine.put(overlay+8,execution);machine.put(overlay+16,main_metadata);machine.uc.mem_write(overlay+20,b'\x01')
        inputs+=1

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resident-elf',type=Path,required=True);p.add_argument('--system-dir',type=Path,required=True)
    args=p.parse_args();elf=Elf(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix='mk61-flash-arm-') as tmp:
        work=Path(tmp);reader=work/'reader'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        packages={kind:package(reader,args.system_dir/name,elf,work,kind) for kind,name in [('tinybasic','BASIC.APP'),('focal','FOCAL.APP'),('language-vm','LANGVM.APP'),('language-input','LANGIN.APP')]}
        for language in (1,2):
            machine=FlashMachine(args.resident_elf,language-1)
            image,io,input_callback=compile_program(machine,packages,elf,language)
            print("ARM frontend compiled",language,len(image),flush=True)
            for address in range(3):
                machine.address_index=address;print('ARM run',language,address,flush=True);execute(machine,packages,image,io,input_callback,language)
            assert machine.max_write==1024 and machine.max_read<=1024
            print(json.dumps(dict(language=language,lines=struct.unpack_from('<H',image,18)[0],image_bytes=len(image),addresses=3,source_window=machine.max_source_read,counts=machine.counts)))
    print('Flash ARM: real frontends + resident index service, >64-KB images, 3 APP addresses, INPUT eviction/resume PASS')
if __name__=='__main__':main()
