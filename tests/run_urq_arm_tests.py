#!/usr/bin/env python3
"""Execute the real M4 URQ/URQUI images, poisoning evicted code at every call.

Only keyboard, menus and files are modeled. ARM EABI, numbers and VM execute
the shipping APPs and resident ELF. Requires Unicorn.
"""

import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[1]))
import argparse
import struct
import tempfile
from pathlib import Path
from unicorn.arm_const import *
from unicorn import UC_HOOK_CODE
from run_app_services_arm_tests import UserMachine, package
from run_portable_system_arm_tests import Elf, ROOT, run
import sys
sys.path.insert(0,str(ROOT/'tools'))
from tools.apps.urq.qst2urq import make_package

class UrqMachine(UserMachine):
    stream=None
    menus=[]
    def __init__(self,*args):
        super().__init__(*args)
        self.uc.hook_del(self.hook_handle)
        for address in {*self.callbacks,*self.basic_display,self.syscall&~1,self.binary_stop,0x080FD000}:
            self.uc.hook_add(UC_HOOK_CODE,self.hook,begin=address,end=address)
    def load_overlay(self,packed):
        self.kind,variants,self.image_size,self.entry,self.crc=packed
        self.base,self.image=variants[self.address_index]
        self.uc.mem_write(self.pool_begin,b'\xCD'*(self.pool_end-self.pool_begin))
        self.uc.mem_write(self.base,self.image)
        self.uc.ctl_remove_cache(self.pool_begin,self.pool_end)
        assert self.call(0,self.api,self.crc,4)==0
    def call(self,command,a=0,b=0,c=0,d=0):
        saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
               UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for i,r in enumerate(saved): self.uc.reg_write(r,0x31410000+i)
        for r,v in zip((UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),
                       (self.stack_top,self.stop|1,command,a,b,c)): self.uc.reg_write(r,v)
        self.put(self.stack_top,d)
        self.uc.emu_start(self.base+self.entry+1,self.stop,timeout=120_000_000,count=500_000_000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==self.stop,('no return',hex(self.uc.reg_read(UC_ARM_REG_PC)),self.stream,self.trace[-15:])
        assert self.uc.reg_read(UC_ARM_REG_SP)==self.stack_top
        for i,r in enumerate(saved): assert self.uc.reg_read(r)==0x31410000+i
        return self.uc.reg_read(UC_ARM_REG_R0)
    def stream_next(self,accepted):
        stream=self.stream
        if stream['count']:
            assert accepted,'save callback failed'
            stream['bytes']+=bytes(self.uc.mem_read(self.input+1536,stream['count']))
        offset=len(stream['bytes'])
        if offset==stream['size']:
            inode=stream['id'] if stream['id']!=0xFFFF else max(self.files)+1
            self.files[inode]=(15,stream['name']+'.urs',stream['bytes'])
            self.put(stream['payload']+16,inode)
            self.uc.reg_write(UC_ARM_REG_R0,1);self.uc.reg_write(UC_ARM_REG_PC,stream['return']);self.stream=None
            return
        stream['count']=min(512,stream['size']-offset)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),
                       (stream['context'],offset,self.input+1536,stream['count'])): self.uc.reg_write(r,v)
        self.uc.reg_write(UC_ARM_REG_LR,0x080FD001);self.uc.reg_write(UC_ARM_REG_PC,stream['callback'])
    def hook(self,uc,address,size,context):
        if address in self.callbacks and self.callbacks[address] in ('key_poll','key_wait') and not self.keys:
            raise AssertionError(('keyboard underflow',bytes(uc.mem_read(self.workspace,40)).hex(),self.trace[-30:]))
        if address==0x080FD000: self.stream_next(bool(uc.reg_read(UC_ARM_REG_R0)));return
        if address==(self.syscall&~1) and uc.reg_read(UC_ARM_REG_R0)==47:
            p=self.words(uc.reg_read(UC_ARM_REG_SP),1)[0]
            name,ctx,callback,length,_=self.words(p,5)
            self.stream={'bytes':b'','count':0,'size':length,'payload':p,'name':self.string(name),
                         'context':ctx,'callback':callback,'id':uc.reg_read(UC_ARM_REG_R2),
                         'return':uc.reg_read(UC_ARM_REG_LR)}
            self.stream_next(True);return
        super().hook(uc,address,size,context)
    def system(self,op,a,b,c,p):
        if op==25 and a==13: return super().system(op,a,b,c,p)|512;
        if op==25 and a==26: return 20000 if b else 43210;
        if op==14 and p not in self.leases:
            # Public leases are value handles; the shell copies its SCRATCH
            # handle to the stack before releasing the memory containing it.
            candidates=[key for key,value in self.leases.items() if value[0]==a]
            assert len(candidates)==1
            self.leases[p]=self.leases.pop(candidates[0])
        if op==1:
            if a==18:self.ui_text=True
            if a==20:self.lines.append(bytes(self.uc.mem_read(p,128)).split(b'\0')[0].decode('cp1251'))
            if a==21:return 5*len(self.string(p))
            if a==22:return 192
            return super().system(op,a,b,c,p)
        if op==19:
            assert c==20 and self.menus,('unexpected menu',self.trace[-10:])
            selected=self.menus.pop(0)
            assert selected<self.words(p+8,1)[0];self.put(p+12,selected);return 1
        return super().system(op,a,b,c,p)

def step(m,packed,inode,phase,keys=(),menus=(),result=0,status=0):
    context,flow=m.input+768,m.input+1024
    m.load_overlay(packed);m.keys=list(keys);m.menus=list(menus)
    m.uc.mem_write(flow,bytes(48));m.put(flow,48,1,context,64)
    m.uc.mem_write(flow+16,struct.pack('<HBBI',inode,4,0,phase));m.put(flow+40,result,status)
    assert m.call(4,flow)==1
    return m.words(flow+32,4)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,required=True)
    parser.add_argument('--apps-dir',type=Path,required=True)
    parser.add_argument('--address',type=int,choices=(0,1,2))
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='urq-arm-') as temp:
        work=Path(temp);reader=work/'reader'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        elf=Elf(args.resident_elf)
        packages=[package(reader,args.apps_dir/(name+'.APP'),elf,work) for name in ('URQ','URQUI')]
        source=b':start\nprecise="1.2345678901234567"*1\nn=0.1+0.2\nfile_content="intro.txt"\ns=""+n\npln #s$\nbtn ask,Go\nend\n:ask\nproc inner\nbtn done,Finish\nend\n:inner\ninput answer\nsave\nstamp=answer\nend\n:done\nquit\n'
        files,_=make_package(source,'urqw','UTF-8',resources={'intro.txt':'Русский текст ресурса'})
        for address in ([args.address] if args.address is not None else range(3)):
            m=UrqMachine(args.resident_elf,True,address)
            m.graphics=False # overlay/state test; pixel UI is qualified separately
            m.files={40:(8,'URQ.APP',b''),41:(8,'URQUI.APP',b''),42:(13,'game.urq',files['game.urq']),43:(14,'p0000.uqd',files['p0000.uqd'])}
            # A helper from this release must reject the earlier shell layout
            # before dereferencing its differently laid-out App object.
            context,flow=m.input+768,m.input+1024
            m.uc.mem_write(flow,bytes(48));m.put(flow,48,1,context,64)
            m.uc.mem_write(flow+16,struct.pack('<HBBI',41,4,0,1))
            for previous_magic in (0x31515255,0x32515255):
                m.put(context,previous_magic,m.workspace,0)
                m.load_overlay(packages[1]);assert m.call(4,flow)==0
            m.load_overlay(packages[0]);assert m.call(5)==0x31574C46
            m.uc.mem_write(m.input+768,bytes(64));m.put(m.input+768,42)
            # Follow the public flow protocol rather than private player
            # phase numbers. Every transition evicts and poisons the old code.
            inode,phase,result,status=40,2,0,0
            stack=[]
            keys=[19,1,23,2,16,24,2,2,25,19,25,19,1]
            menus=[1,1,2,1,5,0]
            snapshots=[]
            for iteration in range(80):
                action,resume,result,status=step(m,packages[inode-40],inode,phase,keys,menus,result,status)
                keys,menus=m.keys,m.menus
                for file in m.files.values():
                    if file[0]==15 and file[2] not in snapshots:snapshots.append(file[2])
                flow=m.input+1024
                if action==2:
                    stack.append((inode,resume))
                    inode=struct.unpack('<H',bytes(m.uc.mem_read(flow+24,2)))[0]
                    phase=m.words(flow+28,1)[0]
                    result,status=0,0
                elif action==3:
                    inode,phase=stack.pop()
                elif action==4:
                    assert not stack and not result and not status
                    break
                else:raise AssertionError(('unexpected flow action',action))
            else:raise AssertionError('URQ did not exit')
            assert not keys and not menus,(keys,menus)
            assert len(snapshots)>=2
            for saved in snapshots:
                assert saved[:6]==b'URQS\x04\0' and b'Ab' in saved
                assert struct.pack('<d',1.2345678901234567) in saved
                assert b'0.30000000000000004' in saved
            assert any(line.startswith('0.300000') for line in m.lines),m.lines
            assert not m.leases and not m.depth

            # A failed helper reload must not leak either resident lease.
            failed=UrqMachine(args.resident_elf,True,address);failed.files=dict(m.files);failed.graphics=False
            failed.uc.mem_write(failed.input+768,bytes(64));failed.put(failed.input+768,42)
            action,resume,_,_=step(failed,packages[0],40,2)
            assert action==2
            helper_phase=failed.words(failed.input+1024+28,1)[0]
            assert step(failed,packages[1],41,helper_phase)[0]==3
            action,resume,_,_=step(failed,packages[0],40,resume)
            assert action==2
            action,_,result,_=step(failed,packages[0],40,resume,result=0,status=1)
            assert action==4 and result and not failed.leases and not failed.depth

            # Navigation and USER during a long running script are forwarded
            # once; the UI must not consume another key before engine progress.
            busy=UrqMachine(args.resident_elf,True,address);busy.files=dict(m.files);busy.graphics=False
            looping,_=make_package(b':start\nx=0\n:loop\nx=x+1\nif x<500 then goto loop\nquit\n','urqw','UTF-8')
            busy.files[42]=(13,'game.urq',looping['game.urq'])
            busy.files[43]=(14,'p0000.uqd',looping['p0000.uqd'])
            busy.uc.mem_write(busy.input+768,bytes(64));busy.put(busy.input+768,42)
            action,resume,_,_=step(busy,packages[0],40,2);assert action==2
            helper_phase=busy.words(busy.input+1024+28,1)[0]
            assert step(busy,packages[1],41,helper_phase)[0]==3
            for key in (16,25):
                action,resume,_,_=step(busy,packages[0],40,resume,[key]);assert action==2 and not busy.keys
                helper_phase=busy.words(busy.input+1024+28,1)[0]
                assert step(busy,packages[1],41,helper_phase,menus=[5,0] if key==25 else ())[0]==3
            action,resume,_,_=step(busy,packages[0],40,resume);assert action==2
            helper_phase=busy.words(busy.input+1024+28,1)[0]
            assert step(busy,packages[1],41,helper_phase)[0]==3
            assert step(busy,packages[0],40,resume)[0]==4
            assert not busy.leases and not busy.depth

            # A submitted special variable needs exact numeric parsing in the
            # engine overlay; the UI overlay only queues the unchanged draft.
            numeric=UrqMachine(args.resident_elf,True,address);numeric.files=dict(m.files);numeric.graphics=False
            special,_=make_package(b':start\ninput style_dos_textcolor\npln #style_textcolor$\nbtn done,Finish\nend\n:done\nquit\n','urqw','UTF-8')
            numeric.files[42]=(13,'game.urq',special['game.urq'])
            numeric.files[43]=(14,'p0000.uqd',special['p0000.uqd'])
            numeric.uc.mem_write(numeric.input+768,bytes(64));numeric.put(numeric.input+768,42)
            inode,phase,result,status=40,2,0,0;stack=[]
            keys,menus=[23,23,4,2,19,25],[5,0] # numeric phone layout, "42", submit, menu/exit
            for iteration in range(40):
                action,resume,result,status=step(numeric,packages[inode-40],inode,phase,keys,menus,result,status)
                keys,menus=numeric.keys,numeric.menus;flow=numeric.input+1024
                if action==2:
                    stack.append((inode,resume))
                    inode=struct.unpack('<H',bytes(numeric.uc.mem_read(flow+24,2)))[0]
                    phase=numeric.words(flow+28,1)[0];result,status=0,0
                elif action==3:inode,phase=stack.pop()
                elif action==4:
                    assert not stack and not result and not status
                    break
                else:raise AssertionError(('unexpected numeric flow action',action))
            else:raise AssertionError('URQ numeric input did not exit')
            assert not keys and not menus and not numeric.leases and not numeric.depth
            assert '#55FF55' in numeric.lines,numeric.lines
        print('URQ ARM: three relocation addresses, poisoned overlay swaps, local exact numbers, SMS, input/procedure saves, restore and clean exit PASS')

if __name__=='__main__':main()
