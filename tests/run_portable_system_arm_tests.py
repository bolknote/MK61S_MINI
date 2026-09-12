#!/usr/bin/env python3
"""Run every System APP against real resident C API tables and ARM helpers.

Only hardware/C5 and workspace backing are mocked. The resident's actual
arithmetic, printf, font decoder and editor key handler execute as ARM code.

Use test-only residents built with MK61_MATH_BACKEND=0 (LIBM). This model does
not initialize the calculator core or implement STM32 bit-band peripherals;
CORE transcendental functions are covered separately by run_mk_math_tests.sh.
Product builds may continue to use MK61_MATH_BACKEND=1.
--ui-only qualifies UI on exact product residents without the transcendental
probe; all display, editor, settings, ABI and ordinary arithmetic checks remain.
"""
import argparse
import binascii
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
    def require_libm_math(self, path):
        # This is the CORE implementation's MatrixKey evaluator, including
        # GCC/LTO clone suffixes. Checking symbols avoids hard-coded addresses
        # and does not require running any firmware in Unicorn first.
        if any('10eval_unaryEdRKNS_9MatrixKeyE' in name for name in self.symbols):
            raise ValueError(
                f'{path}: MK61_MATH_BACKEND=1 (CORE) is unsupported by this '
                'ARM fixture: the calculator core and STM32 bit-band are not '
                'modeled. Build test-only residents with MK61_MATH_BACKEND=0 '
                '(LIBM); run tests/run_mk_math_tests.sh for real CORE math. '
                'Do not change the product configuration.')
        # Fail closed if a stripped or otherwise incompatible ELF does not
        # positively identify the math implementation exercised by this suite.
        required = {'sin', 'cos', 'sqrt', 'exp', 'log'}
        if not required.issubset(self.symbols):
            raise ValueError(
                f'{path}: cannot confirm LIBM math in the resident ELF; '
                'provide an unstripped test-only MK61_MATH_BACKEND=0 build.')
    def load(self, uc):
        for s in self.sections:
            if s[2] & 2 and s[5]:
                uc.mem_write(s[3], bytes(s[5]) if s[1] == 8 else self.data[s[4]:s[4]+s[5]])

def preview_font():
    # FMK1, eight 3x5 monospaced glyphs A..H, literal pixel records.
    data = bytearray(b'FMK1' + bytes((1,3,5,0x31)) + struct.pack('<H',8) + bytes((1,0,0,0,0,0)))
    data += struct.pack('<HB',ord('A'),7)
    data += bytes.fromhex('2bed') * 8  # Literal bit followed by 15 pixel bits.
    struct.pack_into('<H',data,12,len(data))
    struct.pack_into('<H',data,14,binascii.crc_hqx(data,0xffff))
    return bytes(data)


def ui_font_oracle(family, size, text):
    """Reference first paragraph using the reviewed native source pixels."""
    font_dir = ROOT / 'tools/.fmk-font/ui-atlases'
    name = 'roboto' if family == 2 else 'dejavu'
    atlas = json.loads((font_dir / f'{name}-{size}.json').read_text())
    glyphs = {g['codepoint']: g for g in atlas['glyphs']}
    fallback = json.loads((font_dir / f'dejavu-{size}.json').read_text())
    fallback = {g['codepoint']: g for g in fallback['glyphs']}
    frame = bytearray(1536)
    x = 2
    for character in text:
        glyph = glyphs.get(ord(character), fallback.get(ord(character), glyphs[ord('?')]))
        top = 2 + atlas['ascent'] - glyph['bearing_y']
        for y, row in enumerate(glyph['rows']):
            for gx, pixel in enumerate(row):
                if pixel == '1':
                    px, py = x + glyph['safe_bearing_x'] + gx, top + y
                    frame[(py // 8) * 192 + px] |= 1 << (py % 8)
        x += glyph['advance']
    return bytes(frame)


class Machine:
    def __init__(self, resident, graphics, address_index=0):
        self.address_index = address_index
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        self.uc.mem_map(BASE, 131072)
        self.uc.mem_map(0x08000000, 0x100000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        elf = Elf(resident); elf.load(self.uc)
        # setup() normally binds this pointer after the GPIO-dependent LCD
        # constructor. No panel is constructed in this peripheral model, but
        # the real UI-font dispatcher still evaluates its trivial preference
        # getters before serializing GLYPH from the request's own family/size.
        # Bind actual zeroed ELF storage, without guessing a C++ field offset;
        # INFO/current preferences continue to be mocked in system().
        self.put(elf.symbol('main_lcd_pointer'), elf.symbol('mk61_lcd_storage'))
        self.input = elf.symbol('__mk61_dynamic_begin')
        self.pool_begin = (self.input + 2048 + 31) & ~31
        self.pool_end = elf.symbol('__mk61_dynamic_end')
        self.stack_top = elf.symbol('_estack') - 16
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
        self.datetime = [2026, 9, 6, 12, 34, 56]
        self.rtc_writes = []
        self.calibration = 123
        self.profile = bytes((6, 5, 8, 2))
        self.extended = False
        self.ui_fonts = False
        self.ui_font = bytes((0, 14))
        self.ui_text = False
        self.live_ui = True
        self.legacy_rows = 4
        self.setup_rows, self.setup_views = {}, []
        self.revision = 1
        self.drop_live_ui_on_wait = False
        self.ui_ends = 0
        self.font_restores = 0
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
            if a in (20,24,26) or (a == 27 and b == 1):
                self.key_calls += a == 24
                return  # Execute the real resident font/editor/capability dispatcher.
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
            elif name == 'display_rows':
                if not self.graphics:
                    result = 2
                elif not self.ui_text:
                    result = self.legacy_rows
                elif not self.ui_font[0]:
                    result = 4
                else:
                    result = 5 if self.ui_font[1] == 12 else (3 if self.ui_font[1] == 16 else 4)
            elif name == 'display_clear': self.lines = []; result = 1
            elif name == 'display_write_utf8':
                self.lines.append(bytes(uc.mem_read(c,d)).decode('utf8')); result = 1
            elif name in ('key_poll','key_wait'):
                assert self.keys, 'user APP keyboard underflow'
                result = self.keys.pop(0)
            elif name == 'graphics_available': result = self.graphics
            elif name == 'graphics_width': result = 192 if self.graphics else 0
            elif name == 'graphics_height': result = 64 if self.graphics else 0
            elif name == 'graphics_revision': result = self.revision
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
            if a == 0: self.setup_rows = {}
            if a == 3: self.lines.append(self.string(p))
            if a == 2: self.lines.append(chr(b))
            if a == 10: self.viewport_ends += 1
            if a == 15: self.ui_ends += 1; self.ui_text = False
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
        if op == 27:
            # Only the current hardware preference is mocked. The GLYPH case
            # executes the actual resident font service in ARM code above.
            assert a == 0 and c == 6
            family, size = self.ui_font
            if not self.graphics or not family:
                self.uc.mem_write(p, bytes(6))
            else:
                ascent = 13 if size == 16 else (11 if size == 14 else 10)
                gap = 1 if size == 12 else 2
                self.uc.mem_write(p, bytes((family, size, ascent, size - ascent, gap, 0)))
            return 1
        if op == 25:
            if a == 0: return 1
            if a == 1:
                self.put(p, 0x10000423, 256, ord('C'), 7, 3300, 3000, 253, 0, 0)
                self.uc.mem_write(p+36,b'LSI\0'+b'LCD1602'.ljust(16,b'\0')); return 1
            if a == 2: self.put(p,*self.datetime); return 1
            if a == 3:
                self.datetime = list(self.words(p,6)); self.rtc_writes.append(self.datetime); return 1
            if a == 4:
                if b: self.calibration = c - 0x100000000 if c & 0x80000000 else c
                return 1 if b else self.calibration
            if a == 5: self.uc.mem_write(p,self.profile); return 1
            if a == 6: self.profile = bytes(self.uc.mem_read(p,4)); return 1
            if a == 7: return self.graphics
            if a in (8,9): return 1
            if a == 10: self.font_restores += 1; return 1
            if a == 11:
                text = self.string(p)
                self.lines.append(text)
                self.setup_rows[b] = ((chr(c & 255) if c & 256 else '') + text)
                return 1
            if a == 12:
                if b == 2:
                    self.setup_views.append((self.ui_text, self.ui_font, dict(self.setup_rows)))
                    if self.drop_live_ui_on_wait:
                        self.live_ui = False; self.revision += 1
                        self.drop_live_ui_on_wait = False
                return 1
            if a == 13:
                return int(self.graphics) | (2 if self.extended else 0) | (4 if self.ui_fonts else 0) | (8 if self.ui_fonts and self.live_ui else 0)
            if a == 14:
                assert self.ui_fonts
                self.uc.mem_write(p, self.ui_font); return 1
            if a == 15:
                assert self.ui_fonts
                value = bytes(self.uc.mem_read(p, 2))
                assert value[0] <= 2 and value[1] in (12, 14, 16), value
                self.ui_font = value; return 1
            if a == 16:
                assert b in (0, 1)
                if b and not self.live_ui: return 0
                self.ui_text = bool(b); return 1
        raise AssertionError(('unexpected system operation',op,a,b,c))
    def load(self, package):
        self.kind, variants, self.image_size, self.entry, self.crc = package
        self.base, self.image = variants[self.address_index]
        self.uc.mem_write(self.pool_begin,b'\xCD'*(self.pool_end-self.pool_begin))
        self.uc.mem_write(self.base,self.image)
        self.uc.ctl_remove_cache(self.pool_begin, self.pool_end)
        assert self.call(0,self.sys,self.api,self.crc) == 0
    def call(self, command, a=0, b=0, c=0, d=0):
        uc,sp = self.uc,self.stack_top
        saved = [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        for i,r in enumerate(saved): uc.reg_write(r,0x31410000+i)
        saved_fp = [UC_ARM_REG_D8, UC_ARM_REG_D9, UC_ARM_REG_D10, UC_ARM_REG_D11,
                    UC_ARM_REG_D12, UC_ARM_REG_D13, UC_ARM_REG_D14, UC_ARM_REG_D15]
        for i,r in enumerate(saved_fp): uc.reg_write(r,0x3141592600000000+i)
        for r,v in zip([UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],[sp,self.stop|1,command,a,b,c]): uc.reg_write(r,v)
        self.put(sp,d)
        uc.emu_start(self.base+self.entry+1,self.stop,timeout=10_000_000,count=10_000_000)
        assert uc.reg_read(UC_ARM_REG_PC) == self.stop, ('did not return',hex(uc.reg_read(UC_ARM_REG_PC)))
        assert uc.reg_read(UC_ARM_REG_SP) == sp
        for i,r in enumerate(saved): assert uc.reg_read(r) == 0x31410000+i
        for i,r in enumerate(saved_fp): assert uc.reg_read(r) == 0x3141592600000000+i
        assert bytes(uc.mem_read(self.pool_begin,self.base-self.pool_begin)) == b'\xCD'*(self.base-self.pool_begin)
        tail = self.pool_end-self.base-len(self.image)
        if tail: assert bytes(uc.mem_read(self.base+len(self.image),tail)) == b'\xCD'*tail
        assert not self.leases and not self.depth, ('leaked lease',self.leases)
        return uc.reg_read(UC_ARM_REG_R0)
    def source(self, text):
        assert len(text.encode()) < 1024
        self.uc.mem_write(self.input,text.encode()+b'\0'); return self.input


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,action='append',required=True)
    parser.add_argument('--apps-dir',type=Path,required=True)
    parser.add_argument('--expect-public-services',action='store_true',
                        help='verify new adapters require the common API')
    parser.add_argument('--ui-only', action='store_true',
                        help='qualify UI on product residents without the '
                             'transcendental probe; CORE math is tested separately')
    args=parser.parse_args()
    assert len(args.resident_elf) == 2, 'classic graphics, then mini character resident'
    if args.ui_only:
        print('UI qualification (transcendental math separately covered by '
              'core host suite)', flush=True)
    else:
        for resident in args.resident_elf:
            try:
                Elf(resident).require_libm_math(resident)
            except ValueError as error:
                parser.error(str(error))
    with tempfile.TemporaryDirectory(prefix='mk61-system-arm-') as temp:
        reader=Path(temp)/'reader'
        run(['c++','-std=c++17','-O2','-DMK61_ENABLE_PORTABLE_APPS=1','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        for index,resident in enumerate(args.resident_elf):
            elf=Elf(resident)
            low=(elf.symbol('__mk61_dynamic_begin')+2048+31)&~31
            end=elf.symbol('__mk61_dynamic_end')
            packages={}
            for kind,name in [('focal','FOCAL'),('tinybasic','BASIC'),('wbmp-viewer','WBMP'),('markdown-viewer','MARKDOWN'),('chip8','CHIP8'),('markdown-text','MARKDOWN'),('setup','SETUP')]:
                path=args.apps_dir/kind/(name+'.APP'); packed=path.read_bytes()
                target=Path(temp)/(name+'.bin')
                image_size,memory_size,entry=struct.unpack_from('<III',packed,28)
                crc=struct.unpack_from('<I',packed,52)[0]
                high=end-((memory_size+31)&~31)
                assert high >= low, 'APP and input buffer must fit the actual free RAM'
                variants=[]
                for address in (low, ((low+high)//2)&~31, high):
                    run([reader,path,target,hex(address)])
                    variants.append((address,target.read_bytes()))
                packages[kind]=(kind,variants,image_size,entry,crc)
            for address_index in range(3):
                m=Machine(resident,index==0,address_index)
                m.load(packages['focal'])
                if args.expect_public_services:
                    # A poison legacy pointer proves the new adapter uses
                    # query_service; a truncated public table must be refused.
                    assert m.call(0,1,m.api,m.crc) == 0
                    api_size = m.words(m.api+4,1)[0] >> 16
                    m.uc.mem_write(m.api+6,struct.pack('<H',104))
                    assert m.call(0,m.sys,m.api,m.crc) == 5
                    m.uc.mem_write(m.api+6,struct.pack('<H',api_size))
                assert m.call(0x102,m.source('1.10 S A=2+3*4\n1.20 S .R0=A\n1.30 P 100000000\n1.40 P A/3\n1.50 E')) == 1, m.lines
                ui_ends = m.ui_ends
                assert m.call(0x104,0) == 0
                assert m.ui_ends > ui_ends, 'FOCAL must request monospaced output before running'
                assert m.refs[4,0] == 14, m.refs
                assert any('1E+8' in x for x in m.lines), m.lines
                assert any('4.6666667' in x for x in m.lines), m.lines
                m.load(packages['tinybasic'])
                m.keys=[m.mapping[39]]
                # CORE execution requires peripherals absent from this model.
                # UI qualification still exercises the real parser, register
                # writes and ordinary ARM arithmetic, without claiming to test
                # the separately covered transcendental implementation.
                expression = (b'2+4' if args.ui_only else
                              b'SIN(0)+COS(0)+SQRT(16)+LN(EXP(1))')
                m.files[42]=(3,'BTEST',b'10 LET A=6*7\n20 LET .R1=A\n30 .R2=' +
                             expression + b'\n40 PRINT A/3\n50 END\n')
                ui_ends = m.ui_ends
                assert m.call(0x206,42) == 1, (m.lines, m.refs, m.trace[-25:])
                assert m.ui_ends > ui_ends, 'BASIC must request monospaced output before running'
                assert m.refs[4,1] == 42,m.refs
                assert abs(m.refs[4,2]-6) < 1e-6,m.refs
                m.address_index = (m.address_index + 1) % 3
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
                if m.graphics:
                    inline_frames = {}
                    code_frame = None
                    for family, size in ((1, 12), (1, 14), (1, 16),
                                         (2, 12), (2, 14), (2, 16)):
                        m.ui_font = bytes((family, size))
                        text = 'Wi Ёж ←→'
                        m.files[43] = (10, 'README', (text + '\n').encode())
                        m.keys = [m.mapping[39]]; m.frames = []
                        assert m.call(2, 0, 43) == 0
                        assert m.frames == [ui_font_oracle(family, size, text)], (family, size)
                        # Code blocks remain identical across all UI choices.
                        m.files[43] = (10, 'README', b'```\nWi\n```\n')
                        m.keys = [m.mapping[39]]; m.frames = []
                        assert m.call(2, 0, 43) == 0
                        if code_frame is None: code_frame = m.frames
                        assert m.frames == code_frame
                        # Inline code aligns to the selected baseline but is
                        # the same fixed-cell raster for either font family.
                        m.files[43] = (10, 'README', b'`WWii`\n')
                        m.keys = [m.mapping[39]]; m.frames = []
                        assert m.call(2, 0, 43) == 0
                        if size not in inline_frames: inline_frames[size] = m.frames
                        assert m.frames == inline_frames[size]
                    m.ui_font = bytes((0, 14))
                    m.files[43] = (10, 'README', b'# Test\n\nHello **world**.\n')
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
                m.load(packages['setup']); m.lines=[]; m.keys=[m.mapping[37],m.mapping[39]]
                assert m.call(0x400)==0
                assert 'STM32F401' in ''.join(m.lines),m.lines
                m.keys=[m.mapping[39]]; before=list(m.datetime)
                assert m.call(0x401)==0 and not m.rtc_writes and m.datetime==before
                m.keys=[m.mapping[38]]
                assert m.call(0x401)==0 and m.rtc_writes==[before]
                m.keys=[m.mapping[8],m.mapping[38]]
                assert m.call(0x402)==0 and m.calibration==-123,m.calibration
                for extended in (False,True):
                    m.extended=extended; m.profile=bytes((6,5,8,2))
                    m.keys=[m.mapping[41],m.mapping[39]]
                    assert m.call(0x403)==0
                    assert m.profile == (bytes((7,5,8,1)) if extended and m.graphics else
                                         bytes((10,3,5,1)) if m.graphics else bytes((6,5,8,2))),m.profile
                if m.graphics:
                    # Family is first. OK changes a value and ordinary arrows
                    # navigate. Calculator geometry is no longer configurable.
                    for extended in (False, True):
                        m.ui_fonts = True; m.extended = extended
                        m.profile = bytes((6, 5, 8, 2)); m.ui_font = bytes((0, 14))
                        left, right, ok, esc, shg_left, shg_right = m.mapping[36:42]
                        before = len(m.trace)
                        m.keys = [left] * 2 + [right] * 5 + [left] * 5 + [esc]
                        assert m.call(0x403) == 0
                        assert m.profile == bytes((6, 5, 8, 2)) and m.ui_font == bytes((0, 14))
                        assert not [event for event in m.trace[before:] if event[0] == 25 and event[1] in (6, 15)]
                        transitions = ((1, 16, [ok, right, ok, esc]),
                                       (2, 12, [ok, right, ok, esc]),
                                       (0, 12, [ok, esc]))
                        for family, size, keys in transitions:
                            m.keys = keys
                            m.setup_views = []
                            assert m.call(0x403) == 0
                            assert m.ui_font == bytes((family, size)), m.ui_font
                            assert m.profile == bytes((6, 5, 8, 2)), m.profile
                            role, face, rows = m.setup_views[-1]
                            assert role and face == m.ui_font
                            sample_row = 4 if size == 12 and family else (2 if size == 16 and family else 3)
                            assert 'UI font:' in rows[0] and rows[sample_row] == ' Aa Bb Wi 123', rows
                            assert ('UI size:' in rows[1]) == bool(family), rows
                            assert not any('Calculator' in line for line in rows.values()), rows
                        # Even a stale two-row calculator profile cannot change
                        # the font-dependent UI geometry or reopen calculator font controls.
                        m.profile = bytes((6, 5, 8, 2))
                        m.legacy_rows = 2; m.keys = [right, ok, esc]
                        m.setup_views = []; before = len(m.trace)
                        assert m.call(0x403) == 0
                        assert m.profile == bytes((6, 5, 8, 2))
                        assert m.ui_font == bytes((1, 12))
                        fixed_rows = m.setup_views[-1][2]
                        assert fixed_rows[0].startswith('>UI font:')
                        assert fixed_rows[4] == ' Aa Bb Wi 123'
                        assert not [e for e in m.trace[before:] if e[0] == 25 and e[1] in (6, 15)]
                        m.legacy_rows = 4; m.ui_font = bytes((2, 12)); m.profile = bytes((6, 5, 8, 2))
                        # Proportional mode shows only size. OK advances it and
                        # shifted-left reverses it without opening another view.
                        m.keys = [right, ok, shg_left, esc]
                        m.setup_views = []
                        assert m.call(0x403) == 0
                        assert m.profile == bytes((6, 5, 8, 2))
                        assert m.ui_font == bytes((2, 12))
                        assert any(view[1] == bytes((2, 14)) for view in m.setup_views)
                        assert all(view[0] for view in m.setup_views)
                        assert m.setup_views[-1][2][4] == ' Aa Bb Wi 123'
                    # A display revision change to the monospaced USB backend
                    # leaves the live chooser safely without applying settings.
                    m.setup_views = []; m.drop_live_ui_on_wait = True; m.keys = [esc]
                    before = len(m.trace)
                    assert m.call(0x403) == 0 and not m.live_ui
                    assert m.setup_views[0][0]
                    assert not [e for e in m.trace[before:] if e[0] == 25 and e[1] in (6, 15)]
                    m.live_ui = True
                    m.ui_fonts = False
                m.keys=[m.mapping[39]]
                pointer=m.source('bad font'); m.lines=[]
                assert m.call(0x404,pointer,pointer,8)==0
                assert 'Bad font' in ''.join(m.lines),m.lines
                assert m.font_restores>0
                font=preview_font(); pointer=m.input+1024
                m.uc.mem_write(pointer,font); m.keys=[m.mapping[39]]; m.lines=[]
                trace_start=len(m.trace)
                assert m.call(0x404,m.source('TEST'),pointer,len(font))==0
                assert 'f1 3x5 TEST' in ''.join(m.lines),m.lines
                operations=[x[1] for x in m.trace[trace_start:] if x[0]==25]
                if m.graphics:
                    assert 7 in operations and 8 in operations
                else:
                    assert operations.count(9)==8 and 10 in operations
                print(f'{resident}: address variant {address_index}, all six APPs + cross-address language state + SETUP PASS')

if __name__=='__main__': main()
