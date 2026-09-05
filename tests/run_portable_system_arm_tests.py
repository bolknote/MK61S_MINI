#!/usr/bin/env python3
"""Run every System APP against real resident C API tables and ARM helpers.

Only hardware/C5 and workspace backing are mocked. The resident's actual
arithmetic, printf, font decoder and editor key handler execute as ARM code.
"""
import argparse
import json
import struct
import tempfile
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
from run_portable_app_arm_tests import CALLBACKS, ROOT, BASE, OVERLAY, run, wbmp, oracle

class Elf:
    def __init__(self, path):
        self.data = path.read_bytes()
        h = struct.unpack_from('<16sHHIIIIIHHHHHH', self.data)
        assert h[0][:6] == b'\x7fELF\x01\x01' and h[2] == 40
        self.sections = [struct.unpack_from('<10I', self.data, h[6] + i*h[11]) for i in range(h[12])]
        self.symbols = {}
        for s in self.sections:
            if s[1] != 2: continue
            t = self.sections[s[6]]
            names = self.data[t[4]:t[4]+t[5]]
            for off in range(s[4], s[4]+s[5], s[9]):
                n, value, size, _, _, index = struct.unpack_from('<IIIBBH', self.data, off)
                self.symbols[names[n:names.find(b'\0', n)].decode()] = value
    def symbol(self, name):
        found = [v for k,v in self.symbols.items() if name in k]
        assert len(found) == 1, (name, found)
        return found[0]
    def load(self, uc):
        for s in self.sections:
            if s[2] & 2 and s[5]:
                uc.mem_write(s[3], bytes(s[5]) if s[1] == 8 else self.data[s[4]:s[4]+s[5]])

class Machine:
    def __init__(self, resident, graphics):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        self.uc.mem_map(BASE, 65536)
        self.uc.mem_map(0x08000000, 0x100000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        elf = Elf(resident); elf.load(self.uc)
        self.api = elf.symbol('_ZN12loadable_app12_GLOBAL__N_1L3APIE')
        self.sys = elf.symbol('_ZZN15loadable_module10system_apiEvE3api')
        assert struct.unpack('<IHH', self.uc.mem_read(self.sys, 8)) == (0x31535953, 1, 28)
        self.mapping, self.syscall, _, _, _ = self.words(self.sys+8, 5)
        self.mapping = list(self.uc.mem_read(self.mapping, 42))
        self.workspace = elf.symbol('17workspace_storageE')
        self.scratch = elf.symbol('15scratch_storageE')
        self.callbacks = {v & ~1: k for k,v in zip(CALLBACKS,self.words(self.api+12,23))}
        self.stop = 0x080FF000
        self.uc.hook_add(UC_HOOK_CODE, self.hook)
        self.graphics = graphics
        self.files, self.snapshots, self.stamps, self.leases = {}, {}, {}, {}
        self.owner, self.depth = 0, 0
        self.keys, self.frames, self.lines, self.editor_views = [], [], [], []
        self.clock = self.services = self.begins = self.ends = self.viewport_ends = 0
        self.refs = {}
        self.chip_exit = False
        self.key_calls = 0
        self.trace = []
    def words(self, address, count):
        return struct.unpack('<'+'I'*count, self.uc.mem_read(address, count*4))
    def put(self, address, *values):
        self.uc.mem_write(address, struct.pack('<'+'I'*len(values), *[v & 0xFFFFFFFF for v in values]))
    def string(self, address):
        if not address: return ''
        value = bytearray()
        while len(value) < 4096:
            ch = self.uc.mem_read(address+len(value),1)[0]
            if not ch: return value.decode('utf8', errors='replace')
            value.append(ch)
        raise AssertionError('unterminated string')
    def file(self, payload, inode):
        if inode not in self.files: return 0
        kind, name, data = self.files[inode]
        self.put(payload, inode, 0xFFFF, len(data), kind, 0)
        self.uc.mem_write(payload+20, name.encode().ljust(32,b'\0'))
        return 1
    def hook(self, uc, address, size, ctx):
        a,b,c,d = [uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        result = None
        if address == (self.syscall & ~1):
            payload = self.words(uc.reg_read(UC_ARM_REG_SP),1)[0]
            if a in (20,24):
                self.key_calls += a == 24
                return  # Execute the real resident font/editor dispatcher.
            self.trace.append((a,b,c,d))
            result = self.system(a,b,c,d,payload)
        elif address in self.callbacks:
            name = self.callbacks[address]
            self.trace.append((name,a,b,c,d))
            result = 0
            if name == 'file_size': result = len(self.files[a][2]) if a in self.files else 0xFFFFFFFF
            elif name == 'file_read':
                if a not in self.files: result = 0xFFFFFFFF
                else:
                    chunk = self.files[a][2][b:b+d]; uc.mem_write(c, chunk); result = len(chunk)
            elif name == 'millis_ms': self.clock += 2; result = self.clock
            elif name == 'service': self.clock += 2; self.services += 1
            elif name == 'delay_ms': self.clock += a
            elif name == 'display_columns': result = 16
            elif name == 'display_rows': result = 4 if self.graphics else 2
            elif name == 'graphics_available': result = self.graphics
            elif name == 'graphics_width': result = 192 if self.graphics else 0
            elif name == 'graphics_height': result = 64 if self.graphics else 0
            elif name == 'graphics_revision': result = 1
            elif name == 'graphics_begin': self.begins += 1; result = self.graphics
            elif name == 'graphics_end': self.ends += 1
            elif name == 'graphics_present':
                assert b == 1536
                self.frames.append(bytes(uc.mem_read(a,b))); result = 1
            elif name in ('beep','sound_stop'): pass
            else: raise AssertionError(('unexpected base callback', name))
        if result is not None:
            uc.reg_write(UC_ARM_REG_R0, int(result)&0xFFFFFFFF)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    def system(self, op, a, b, c, p):
        if op == 1:
            if a == 3: self.lines.append(self.string(p))
            if a == 2: self.lines.append(chr(b))
            if a == 10: self.viewport_ends += 1
            return {6:1,11:self.graphics,12:192 if self.graphics else 0,13:64 if self.graphics else 0,14:self.graphics}.get(a,0)
        if op == 2:
            if a in (0,1,2):
                assert self.keys, ('keyboard underflow', self.kind, a)
                return self.keys.pop(0)
            if a in (3,4): return self.chip_exit and self.services > 20 and b == self.mapping[39]
            if a == 11: return -1
            return 0
        if op == 3: return {0:0,1:50,2:11,3:1}[a]
        if op == 4: return 0x31415926
        if op == 5: self.clock += 2; return self.clock*1000
        if op == 6: return sum(x[0] == a for x in self.files.values())
        if op == 7:
            ids = [i for i,x in self.files.items() if x[0] == c]
            return self.file(p,b if a == 0 else ids[b]) if a == 0 or b < len(ids) else 0
        if op == 8:
            name = self.string(c)
            for i,x in self.files.items():
                if x[0] == b and x[1] == name: self.file(p,i); return 0
            return 4
        if op == 9:
            name,data,length,_ = self.words(p,4)
            inode = b if b != 0xFFFF else max([100,*self.files])+1
            self.files[inode] = (c,self.string(name),bytes(self.uc.mem_read(data,length)))
            self.put(p+12,inode); return 1
        if op == 10:
            if not p: self.files.pop(a,None)
            return 1
        if op == 11: return 0 # Cancel a file chooser.
        if op == 13:
            if a == 0:
                crc = self.words(p+44,1)[0]
                if self.depth and self.owner != b: return 0
                fresh = not self.depth and (b not in self.snapshots or self.stamps.get(b) != crc)
                if not self.depth and self.owner != b:
                    self.uc.mem_write(self.workspace,self.snapshots.get(b,bytes(8192)))
                self.owner = b; self.depth += 1; self.stamps[b] = crc
                address,capacity = self.workspace,8192
            else: address,capacity,fresh = self.scratch,1600,True
            assert c <= capacity
            self.leases[p] = (a,b)
            self.put(p+32,address,capacity,fresh)
            return 1
        if op == 14:
            arena,owner = self.leases.pop(p)
            self.put(p+32,0,0)
            if arena == 0:
                self.depth -= 1
                self.snapshots[owner] = bytes(self.uc.mem_read(self.workspace,8192))
            return 1
        if op == 15: assert self.depth and self.owner == a; return self.workspace
        if op == 16:
            self.lines += [self.string(x) for x in self.words(p,a)]; return 1
        if op in (17,18):
            if op == 17: self.editor_views.append(self.string(self.words(p,1)[0]))
            return 1
        if op == 21:
            self.uc.mem_write(p,struct.pack('<d',self.refs.get((a,b),0))); return 1
        if op == 22: self.refs[a,b] = struct.unpack('<d',self.uc.mem_read(p,8))[0]; return 1
        if op == 23: return any(x[:2] == (a,self.string(p)) for x in self.files.values())
        raise AssertionError(('unexpected system operation',op,a,b,c))
    def load(self, package):
        self.kind, self.image, self.image_size, self.entry, self.crc = package
        self.uc.mem_write(BASE,b'\xCD'*OVERLAY)
        self.uc.mem_write(BASE,self.image)
        self.uc.ctl_remove_cache(BASE, BASE + OVERLAY)
        assert self.call(0,self.sys,self.api,self.crc) == 0
    def call(self, command, a=0, b=0, c=0, d=0):
        uc,sp = self.uc,0x2000FFF0
        saved = [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for i,r in enumerate(saved): uc.reg_write(r,0x31410000+i)
        saved_fp = [UC_ARM_REG_D8, UC_ARM_REG_D9, UC_ARM_REG_D10, UC_ARM_REG_D11,
                    UC_ARM_REG_D12, UC_ARM_REG_D13, UC_ARM_REG_D14, UC_ARM_REG_D15]
        for i,r in enumerate(saved_fp): uc.reg_write(r,0x3141592600000000+i)
        for r,v in zip([UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],[sp,self.stop|1,command,a,b,c]): uc.reg_write(r,v)
        self.put(sp,d)
        uc.emu_start(BASE+self.entry+1,self.stop,timeout=10_000_000,count=10_000_000)
        assert uc.reg_read(UC_ARM_REG_PC) == self.stop, ('did not return',hex(uc.reg_read(UC_ARM_REG_PC)))
        assert uc.reg_read(UC_ARM_REG_SP) == sp
        for i,r in enumerate(saved): assert uc.reg_read(r) == 0x31410000+i
        for i,r in enumerate(saved_fp): assert uc.reg_read(r) == 0x3141592600000000+i
        assert bytes(uc.mem_read(BASE+len(self.image),OVERLAY-len(self.image))) == b'\xCD'*(OVERLAY-len(self.image))
        assert not self.leases and not self.depth, ('leaked lease',self.leases)
        return uc.reg_read(UC_ARM_REG_R0)
    def source(self, text):
        self.uc.mem_write(0x2000D000,text.encode()+b'\0'); return 0x2000D000


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,action='append',required=True)
    parser.add_argument('--apps-dir',type=Path,required=True)
    args=parser.parse_args()
    assert len(args.resident_elf) == 2, 'classic graphics, then mini character resident'
    with tempfile.TemporaryDirectory(prefix='mk61-system-arm-') as temp:
        reader=Path(temp)/'reader'
        run(['c++','-std=c++17','-O2','-DMK61_ENABLE_PORTABLE_APPS=1','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        packages={}
        for kind,name in [('focal','FOCAL'),('tinybasic','BASIC'),('wbmp-viewer','WBMP'),('markdown-viewer','MARKDOWN'),('chip8','CHIP8'),('markdown-text','MARKDOWN')]:
            path=args.apps_dir/kind/(name+'.APP'); packed=path.read_bytes()
            target=Path(temp)/(name+'.bin'); run([reader,path,target])
            image_size,_,entry=struct.unpack_from('<III',packed,28)
            crc=struct.unpack_from('<I',packed,52)[0]
            packages[kind]=(kind,target.read_bytes(),image_size,entry,crc)
        for index,resident in enumerate(args.resident_elf):
            m=Machine(resident,index==0)
            m.load(packages['focal'])
            assert m.call(0x102,m.source('1.10 S A=2+3*4\n1.20 S .R0=A\n1.30 P 100000000\n1.40 P A/3\n1.50 E')) == 1, m.lines
            assert m.call(0x104,0) == 0
            assert m.refs[4,0] == 14, m.refs
            assert any('1E+8' in x for x in m.lines), m.lines
            assert any('4.6666667' in x for x in m.lines), m.lines
            m.load(packages['tinybasic'])
            m.keys=[m.mapping[39]]
            m.files[42]=(3,'BTEST',b'10 LET A=6*7\n20 LET .R1=A\n30 .R2=SIN(0)+COS(0)+SQRT(16)+LN(EXP(1))\n40 PRINT A/3\n50 END\n')
            assert m.call(0x206,42) == 1, (m.lines, m.refs, m.trace[-25:])
            assert m.refs[4,1] == 42,m.refs
            assert abs(m.refs[4,2]-6) < 1e-6,m.refs
            m.load(packages['focal'])
            assert m.call(0x103) == 1
            assert m.call(0x104,0) == 0
            assert m.refs[4,0] == 14
            # Exercise actual resident editor + callbacks back into the APP.
            for kind,edit in [('focal',0x107),('tinybasic',0x207)]:
                m.load(packages[kind]); m.keys=[m.mapping[11],m.mapping[11],m.mapping[36],m.mapping[39],m.mapping[39]]
                # Reuse an existing file; edit-id avoids the directory chooser.
                inode=next(i for i,x in m.files.items() if x[0] == (2 if kind=='focal' else 3))
                assert m.call(edit+2,inode) == 1
                assert m.viewport_ends > 0
            assert m.key_calls >= 4
            # View WBMP with exact pixel checks and unsupported-display fallback.
            m.files[42]=(7,'WIDE',wbmp(208,48)); m.keys=[m.mapping[37],m.mapping[37],m.mapping[39]]
            m.load(packages['wbmp-viewer']); m.frames=[]
            result=m.call(2,0,42)
            assert result == (0 if m.graphics else 2),result
            if m.graphics: assert m.frames == [oracle(208,48,x) for x in (0,8,16)]
            m.load(packages['markdown-viewer']);m.files[43]=(10,'README',b'# Test\n\nHello **world**.\n');m.keys=([m.mapping[39]] if m.graphics else [m.mapping[37],m.mapping[39]])
            assert m.call(2,0,43)==0
            assert m.frames if m.graphics else any('Hello' in x for x in m.lines)
            m.load(packages['markdown-text']); m.lines=[]
            m.keys=([m.mapping[39]] if m.graphics else [m.mapping[37],m.mapping[39]])
            assert m.call(2,0,43)==0
            assert any('Hello' in line for line in m.lines), m.lines
            m.load(packages['chip8']);m.files[44]=(9,'LOOP',bytes.fromhex('00e01200'));m.chip_exit=True;m.services=0
            assert m.call(2,0,44)==(0 if m.graphics else 2)
            # An old/truncated System API is refused before callbacks run.
            before=len(m.trace)
            m.uc.mem_write(m.sys+6,struct.pack('<H',24))
            assert m.call(0,m.sys,m.api,m.crc) == 5
            assert len(m.trace) == before
            m.uc.mem_write(m.sys+6,struct.pack('<H',28))
            print(f'{resident}: all five APPs, arithmetic/state/editor/WBMP/Markdown/CHIP8 PASS')

if __name__=='__main__': main()
