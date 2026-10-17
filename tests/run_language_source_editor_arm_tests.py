#!/usr/bin/env python3
"""Real ARM source editor and compiler handoff, with bounded storage fixtures."""
import argparse
import re
import struct
import tempfile
from pathlib import Path
from unicorn import UC_HOOK_MEM_INVALID
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP
from run_app_flow_arm_tests import FlowMachine, FLOW_STEP, LANGUAGE_FLOW_MAGIC, execute
from run_language_vm_arm_tests import package
from run_portable_system_arm_tests import ROOT, Elf, run

body=(ROOT/'code/loadable_app_services.h').read_text().split('enum mk61_service_usbdisk_operation {',1)[1].split('};',1)[0]
body=re.sub(r'/\*.*?\*/','',body,flags=re.S)
OPS={name:i for i,name in enumerate(re.findall(r'MK61_USBDISK_[A-Z0-9_]+',body))}

class EditorMachine(FlowMachine):
    def __init__(self,*args):
        super().__init__(*args)
        self.catalog_revision=1
        self.pages={}
        self.locked=False
        self.write_pending=None
        self.page_writes=0
        self.fail_page=False
        self.writer_stop=self.stop-0x80
        self.uc.mem_write(self.writer_stop,b'\x70\x47')
        self.call_instruction_limit=100_000_000
        self.call_timeout_us=60_000_000
        self.uc.hook_add(UC_HOOK_MEM_INVALID,self.invalid)
    def invalid(self,uc,access,address,size,value,ctx):
        raise AssertionError(('unmapped editor access',hex(address),size,
            'pc',hex(uc.reg_read(UC_ARM_REG_PC)),'sp',hex(uc.reg_read(UC_ARM_REG_SP)),
            'lr',hex(uc.reg_read(UC_ARM_REG_LR)),self.trace[-8:]))
    def call(self,*args):
        try:return super().call(*args)
        except Exception:
            print('editor ARM failure',hex(self.uc.reg_read(UC_ARM_REG_PC)),
                hex(self.uc.reg_read(UC_ARM_REG_LR)),hex(self.base),self.kind,
                [hex(self.uc.reg_read(r)) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)],
                self.trace[-10:],flush=True)
            raise
    def hook(self,uc,address,size,ctx):
        if address==self.writer_stop:
            self.writer_next(bool(uc.reg_read(UC_ARM_REG_R0)))
            return
        # Only service boundaries need the peripheral fixture. Keep exact
        # per-instruction stack peaks without four extra register reads for
        # each byte scanned by the real APP's parser or editor.
        if (address not in self.callbacks and address not in self.basic_display and
                address not in (self.syscall&~1,self.binary_stop,self.debug_capability_return) and
                (not self.float_return or address!=self.float_return[0])):
            self.stage_peaks[self.stage]=max(self.stage_peaks.get(self.stage,0),
                self.stack_top-uc.reg_read(UC_ARM_REG_SP))
            return
        return super().hook(uc,address,size,ctx)
    def writer_next(self,accepted):
        s=self.write_pending
        if accepted and s['count']:
            s['bytes']+=bytes(self.uc.mem_read(s['buffer'],s['count']))
            s['offset']+=s['count']
        if not accepted or s['offset']==s['size']:
            if accepted:
                inode=s['preferred'] if s['preferred']!=0xFFFF else 99
                self.files[inode]=(s['type'],s['name'],bytes(s['bytes']))
                self.put(s['request']+16,inode)
                self.catalog_revision+=1;self.resource_revision+=1
            self.write_pending=None
            self.uc.reg_write(UC_ARM_REG_R0,int(accepted))
            self.uc.reg_write(UC_ARM_REG_PC,s['return'])
            return
        s['count']=min(64,s['size']-s['offset'])
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),
                             (s['context'],s['offset'],s['buffer'],s['count'])):
            self.uc.reg_write(reg,value)
        self.uc.reg_write(UC_ARM_REG_LR,self.writer_stop|1)
        self.uc.reg_write(UC_ARM_REG_PC,s['callback'])
    def system(self,op,a,b,c,p):
        if op==13 and self.partitioned and self.kind=='application':
            assert b in (1,2),'editor must borrow a cache-free compiler prefix'
        if op==8 and self.string(c)=='/System/SRCEDIT.APP':
            assert self.file(p,77);return 0
        if op==12:return 1
        if op==33:
            if a==OPS['MK61_USBDISK_STAGE_LOCK']:
                if self.locked and b:return 0
                self.locked=True;return 1
            if a==OPS['MK61_USBDISK_STAGE_UNLOCK']:
                self.locked=False;return 1
            if a==OPS['MK61_USBDISK_STAGE_FORGET']:
                for key in range(b,b+c):self.pages.pop(key,None)
                return 1
            if a==OPS['MK61_USBDISK_STAGE_COUNT']:return len(self.pages)
            if a==OPS['MK61_USBDISK_STAGE_NARROW_MATCHING']:return 1
            if a==OPS['MK61_USBDISK_STAGE_EXISTS']:return int(b in self.pages)
            if a==OPS['MK61_USBDISK_STAGE_WRITE']:
                assert self.locked
                if self.fail_page:return 0
                self.pages[b]=bytes(self.uc.mem_read(p,512));self.page_writes+=1
                self.resource_revision+=1;return 1
            if a==OPS['MK61_USBDISK_STAGE_READ']:
                if b not in self.pages:return 0
                self.uc.mem_write(p,self.pages[b]);return 1
            if a==OPS['MK61_USBDISK_C9_WRITE_FILE_SOURCE']:
                parent,preferred,kind,size,_,count,name,context,callback,*_=self.words(p,13)
                assert not count and self.base<=(callback&~1)<self.base+self.image_size
                self.write_pending=dict(request=p,preferred=preferred,type=kind,size=size,
                    name=self.string(name),context=context,callback=callback,offset=0,count=0,
                    buffer=self.input+1536,bytes=bytearray(),**{'return':self.uc.reg_read(UC_ARM_REG_LR)})
                self.writer_next(True);return None
            raise AssertionError(('source editor used an unexpected store operation',a))
        return super().system(op,a,b,c,p)

def edit(m,packages,language,source,save=True,fail=False):
    context,step,values=m.input+768,m.input+1120,m.workspace+4176
    m.partitioned=True;m.fail_page=fail
    m.files[42]=(3 if language==1 else 2,'EDIT',source)
    m.files[77]=(8,'SRCEDIT',packages['editor_file'])
    m.uc.mem_write(values,b'\x5A'*4016);m.uc.mem_write(values+4,b'\xFF'*4)
    original_values=bytes(m.uc.mem_read(values,4016))
    m.uc.mem_write(context,bytes(240));m.put(context,LANGUAGE_FLOW_MAGIC,0)
    command=0x209 if language==1 else 0x109
    m.put(context+76,values,command,42,0)
    m.uc.mem_write(context+234,bytes((language,)))
    m.load(packages['tinybasic' if language==1 else 'focal'])
    m.uc.mem_write(step,bytes(48));m.put(step,48,1,context,240)
    m.uc.mem_write(step+16,struct.pack('<HBBI',0xFFFF,2 if language==1 else 1,0,0x100))
    assert m.call(FLOW_STEP,step)==1
    assert struct.unpack('<HBBI',m.uc.mem_read(step+24,8))==(77,4,0,0x102)
    assert m.words(step+32,1)==(1,)
    assert m.uc.mem_read(context+42,1)==b'\x01'
    at=33000
    m.uc.mem_write(context+30,struct.pack('<H',at))
    # Insert in a long comment, then move to the next physical line. This
    # forces a draft flush and a new window before Save/Cancel.
    m.keys=[m.mapping[17],m.mapping[41],m.mapping[39],m.mapping[38 if save else 39]]
    m.load(packages['source-editor'])
    m.uc.mem_write(step,bytes(48));m.put(step,48,1,context,240)
    m.uc.mem_write(step+16,struct.pack('<HBBI',77,4,0,0x102))
    assert m.call(FLOW_STEP,step)==1
    assert m.words(step+32,4)==(4,0,1,0)
    assert not m.pages and not m.locked and not m.depth
    assert bytes(m.uc.mem_read(values,4))==original_values[:4]
    assert bytes(m.uc.mem_read(values+8,4008))==original_values[8:]
    actual=m.files[42][2]
    if save and not fail:
        expected=source[:at]+b'7'+source[at:]
        if language==2:expected=expected.replace(b'COMMENT',b'C').replace(b'EXIT',b'E').replace(b'SET',b'S')
        assert actual==expected,(language,len(actual),len(expected))
        assert m.page_writes and m.catalog_revision==2
    else:assert actual==source and m.catalog_revision==1
    assert all(x[4]<=256 for x in m.trace if x[0]=='source_read')
    return {'language':language,'saved':save,'failed_page':fail,'page_writes':m.page_writes,
            'stack_peak':max(m.stage_peaks.values())}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resident-elf',type=Path,required=True);p.add_argument('--system',type=Path,required=True)
    args=p.parse_args();elf=Elf(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix='mk61-source-editor-arm-') as directory:
        work=Path(directory);reader=work/'reader'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        packages={kind:package(reader,args.system/name,elf,work,kind) for kind,name in
                  [('tinybasic','BASIC.APP'),('focal','FOCAL.APP'),('source-editor','SRCEDIT.APP'),
                   ('language-vm','LANGVM.APP'),('language-input','LANGIN.APP')]}
        packages['source-editor']=('application',*packages['source-editor'][1:])
        packages['editor_file']=(args.system/'SRCEDIT.APP').read_bytes()
        for address in range(3):
            for language in (1,2):
                source=(b'10 REM ' if language==1 else b'1.01 COMMENT ')+b'x'*34000+(
                    b'\n20 A=42;END\n' if language==1 else b'\n1.02 SET A=42;EXIT\n')
                for save,fail in ([(True,False),(False,False),(True,True)] if address==0 else [(True,False)]):
                    result=edit(EditorMachine(args.resident_elf,True,address),packages,language,source,save,fail)
                    print(address,result,flush=True)
        for language in (1,2):
            head=b'10 REM ' if language==1 else b'1.01 C '
            tail=b'\n20 @(384)=42;A=@(384)+SIZE-768;END\n' if language==1 else b'\n1.02 S A=42;E\n'
            source=head+b'x'*(65534-len(head)-len(tail))+tail
            machine=EditorMachine(args.resident_elf,True,0)
            value,*_=execute(machine,packages,language,source,[])
            assert value==42
            assert all(x[4]<=256 for x in machine.trace if x[0]=='source_read')
            print('64 KiB compiler/VM',language,'PASS',flush=True)
    print('ARM paged editor: compiler handoff, 34 KiB sources, operator view, draft pages, Save/Cancel/I/O, retained values and three load addresses PASS')
if __name__=='__main__':main()
