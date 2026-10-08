#!/usr/bin/env python3
"""Execute packed SHEET.APP with real ARM resident fonts, numbers and math.

Keyboard, display and storage hardware are modeled; code and shared services
execute in Unicorn. Requires the same environment as the other ARM tests.
"""
import argparse
import binascii
import re
import struct
import tempfile
from pathlib import Path

from run_app_services_arm_tests import UserMachine, package
from run_portable_system_arm_tests import Elf, ROOT, run


class SheetMachine(UserMachine):
    def system(self, op, a, b, c, p):
        if op == 12:
            assert a == 12  # S1 file type, public FILE_SAVE_TARGET
            return 1
        return super().system(op,a,b,c,p)


def cells(data):
    assert data[:4] == b'MKSH' and data[4] == 1
    at, result = 20, {}
    for _ in range(data[9]):
        position, kind, length = struct.unpack_from('<HBB',data,at)
        at += 4
        result[position] = (kind,data[at:at+length].decode('cp1251'))
        at += length
    assert at == len(data)
    return result


def shows_selected_nine(frames):
    source=(ROOT/'code/ERM19264_graphics_font.cpp').read_text()
    table=re.search(r'UC_Font_One\[\][^{]*\{(.*?)\n\};',source,re.S).group(1)
    table=re.sub(r'//[^\n]*','',table)
    font=[int(value,16) for value in re.findall(r'0x[0-9A-Fa-f]+',table)]
    glyph=font[ord('9')*5:ord('9')*5+5]
    expected=[int(not (glyph[x] & (1<<y))) for y in range(8) for x in range(5)]
    # A1's numeric value is right-aligned in the selected inverse cell.
    return any([(frame[((16+y)//8)*192+66+x]>>((16+y)%8))&1
                for y in range(8) for x in range(5)]==expected for frame in frames)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,action='append',required=True)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--address',type=int,choices=(0,1,2),help='run one relocation address while diagnosing')
    args=parser.parse_args()
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    from build_sheet_app import document
    with tempfile.TemporaryDirectory(prefix='mk61-sheet-arm-') as directory:
        work=Path(directory); reader=work/'reader'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        for resident in args.resident_elf:
            elf=Elf(resident); elf.require_libm_math(resident)
            packed=package(reader,args.app,elf,work)
            for address in ([args.address] if args.address is not None else range(3)):
                machine=SheetMachine(resident,True,address)
                machine.call_instruction_limit=100_000_000
                machine.call_timeout_us=60_000_000
                assert machine.load_user(packed)==0
                enter=256+machine.mapping[1]
                # A1=2, B1=125, C1=A1 ENT B1 *, then save and exit.
                machine.keys=[2,19,16,1,2,5,19,16,19,25,15,15,19,enter,25,15,19,13,19,20,19]
                assert machine.call(1,machine.api)==0
                assert machine.begins==machine.ends and len(machine.frames)>10
                inode=max(machine.files)
                assert machine.files[inode][0]==12
                assert cells(machine.files[inode][2])=={0:(1,'2'),1:(1,'125'),2:(3,'A1 ENT B1 *')}
                saved=machine.files[inode][2]
                assert struct.unpack_from('<I',saved,16)[0]==binascii.crc32(saved[:16]+saved[20:])
                # Reopen and change B1, save through the existing id.
                machine.keys=[16,2,19,20,19]
                reopened=machine.call(2,machine.api,inode)
                assert reopened==0,(reopened,machine.trace[-25:],machine.keys,saved.hex())
                assert cells(machine.files[inode][2])[1]==(1,'2')
                # A real resident SQRT runs before the leased framebuffer.
                machine.keys=[8,1,24,12,19,20,16,19]
                machine.frames=[]
                assert machine.call(1,machine.api)==0
                assert shows_selected_nine(machine.frames)
                # Russian phone input needs no prefix: РОСТ, including two
                # consecutive letters from the same keypad group.
                machine.keys=[25,16,16,16,16,19,16,19,
                              6,5,5,5,6,6,16,6,6,6,19,20,19]
                assert machine.call(1,machine.api)==0
                text_inode=max(machine.files)
                assert cells(machine.files[text_inode][2])=={0:(2,'РОСТ')}
                machine.keys=[20]
                assert machine.call(2,machine.api,text_inode)==0
                # MK-61 x^y operand order, with the real resident POW service.
                machine.keys=[2,enter,3,24,256+machine.mapping[5],19,20,16,19]
                machine.frames=[]
                assert machine.call(1,machine.api)==0
                assert shows_selected_nine(machine.frames)
                # A malicious-looking 64-cell dependency ring terminates.
                ring=[]
                for i in range(64):
                    j=(i+1)%64
                    ring.append((f'{chr(65+i%16)}{i//16+1}',3,f'{chr(65+j%16)}{j//16+1}'))
                machine.files[200]=(12,'CYCLE',bytes(document(ring)))
                machine.keys=[20]
                assert machine.call(2,machine.api,200)==0
                # CRC failure never enters the UI and returns INVALID_FILE.
                broken=bytearray(machine.files[200][2]);broken[-1]^=1
                machine.files[201]=(12,'BROKEN',bytes(broken));machine.keys=[]
                assert machine.call(2,machine.api,201)==1
                assert machine.begins==machine.ends
            count=1 if args.address is not None else 3
            print(f'{resident.parent.name}: SHEET at {count} address(es); real ARM runtime, fonts, numbers, math, Russian phone input/save/reopen, 64-cell cycles and CRC rejection PASS')


if __name__=='__main__':
    main()
