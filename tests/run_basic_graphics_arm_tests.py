#!/usr/bin/env python3
"""Real ARM BASIC parsers, resident raster/font and relocated APP callbacks.

GPIO/display and storage are fixtures. VM INPUT evicts both compiler and hot
executor; the resident canvas must survive while their SRAM is poisoned.
"""
import argparse
import tempfile
from pathlib import Path
from run_language_vm_arm_tests import package
from run_language_vm_overlay_arm_tests import OverlayMachine, execute
from run_portable_system_arm_tests import Elf, ROOT, run


def pixel(frame, width, x, y):
    return bool(frame[y//8*width+x] & (1 << (y%8)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,required=True)
    parser.add_argument('--system',type=Path,required=True)
    parser.add_argument('--native-basic',type=Path,required=True)
    args=parser.parse_args()
    elf=Elf(args.resident_elf)
    elf.require_binary64_math(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix='mk61-basic-graphics-arm-') as directory:
        work=Path(directory);reader=work/'reader'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'),
             ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp',ROOT/'code/zx0.cpp','-o',reader])
        packages={kind:package(reader,args.system/name,elf,work,kind)
                  for kind,name in (('tinybasic','BASIC.APP'),('language-vm','LANGVM.APP'),
                                    ('language-input','LANGIN.APP'))}
        native=package(reader,args.native_basic,elf,work,'tinybasic')
        # A prior ABI-6 resident lacks the new synchronous BASIC frontend.
        # Reject both BASIC placements before any source or callbacks run.
        for packed in (native,packages['tinybasic']):
            machine=OverlayMachine(args.resident_elf,True,0)
            machine.service_capabilities_mask=0xFFFFFFFF ^ (1 << 20)
            machine.kind,variants,machine.image_size,machine.entry,machine.crc=packed
            machine.base,machine.image=variants[0]
            machine.uc.mem_write(machine.pool_begin,b'\xCD'*(machine.pool_end-machine.pool_begin))
            machine.uc.mem_write(machine.base,machine.image)
            machine.uc.ctl_remove_cache(machine.pool_begin,machine.pool_end)
            assert machine.call(0,machine.api,machine.crc,2)!=0,'BASIC accepted a missing resident frontend'
            assert not machine.frames
        for address in range(3):
            for width,height in ((80,16),(192,64)):
                for mode in ('native','vm'):
                    def perform(source,answers=(),expected=1):
                        machine=OverlayMachine(args.resident_elf,True,address)
                        machine.graphics_dimensions=(width,height)
                        # A complete GRAPH reparses up to 192 expressions in
                        # the native APP. Allow for the peripheral model and
                        # other ARM qualification runners sharing the host.
                        machine.call_timeout_us=30_000_000
                        if mode=='vm':
                            result=execute(machine,packages,1,source,list(answers))
                            assert result[1]==(0 if expected==1 else expected),(result,machine.lines)
                        else:
                            machine.files[42]=(3,'GRAPHICS',source)
                            machine.load(native)
                            if answers:machine.input_keys(answers[0])
                            status=machine.call(0x20A,42,1)
                            assert status==expected,(status,machine.lines,machine.trace[-12:])
                        return machine
                    machine=perform(b'10 CLS\n20 PSET 1,1\n30 LINE 0,GH-1,GW-1,GH-1\n'
                        b'40 BOX 3,3,7,7,1,1\n50 CIRCLE 20,8,3\n'
                        b'60 PRINT AT 30,0;"A"\n70 SHOW\n'
                        b'80 IF POINT(1,1)<>1 A=1/0\n')
                    frame=machine.frames[-1]
                    assert len(frame)==width*height//8
                    assert pixel(frame,width,1,1) and pixel(frame,width,4,4)
                    assert pixel(frame,width,20,5) and pixel(frame,width,width-1,height-1)
                    assert any(pixel(frame,width,x,y) for x in range(30,35) for y in range(8))
                    assert not any(pixel(frame,width,35,y) for y in range(8))
                    machine=perform(b'10 X=42:CLS:GRAPH X+0+0+0,-1,1,-1,1\n'
                        b'20 IF X<>42 A=1/0\n')
                    frame=machine.frames[-1]
                    assert pixel(frame,width,0,height-1) and pixel(frame,width,width-1,0)
                    machine=perform(b'10 CLS:PSET GW-1,GH-1\n20 INPUT N\n'
                        b'30 IF POINT(GW-1,GH-1)<>1 A=1/0\n40 A=N\n',['7'])
                    assert len(machine.frames)>=2 and pixel(machine.frames[-1],width,width-1,height-1)
                    machine=perform(b'10 CLS:PRINT AT 2,0;CALL(100):END\n'
                        b'100 PRINT AT 30,0;"A"\n110 RETURN 7\n')
                    frame=machine.frames[-1]
                    assert any(pixel(frame,width,x,y) for x in range(2,7) for y in range(8))
                    assert any(pixel(frame,width,x,y) for x in range(30,35) for y in range(8))
                    perform(b'10 X=77:GRAPH 1/0,-1,1,-1,1\n20 IF X<>77 A=1/0\n')
        print('BASIC graphics ARM: native/VM, 3 relocations, 80x16/192x64, pixels, fonts, GRAPH, nested PRINT AT, INPUT eviction PASS')


if __name__=='__main__':
    main()
