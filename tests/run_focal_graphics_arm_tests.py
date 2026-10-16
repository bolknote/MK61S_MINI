#!/usr/bin/env python3
"""FOCAL graphics through real ARM compiler, VM, INPUT and resident raster/font.

Only display/storage/keyboard boundaries are modeled. Each APP replacement
poisons the preceding image; numeric ASK must preserve the resident canvas.
"""
import argparse
import binascii
import json
import struct
import tempfile
import zlib
from pathlib import Path
from run_app_flow_arm_tests import execute as flow_execute
from run_language_vm_overlay_arm_tests import OverlayMachine, execute
from run_language_vm_arm_tests import package
from run_portable_system_arm_tests import Elf, ROOT, run


def pixel(frame, width, x, y):
    return bool(frame[y // 8 * width + x] & (1 << (y % 8)))


def png(path, frame, width, height, scale=4):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', binascii.crc32(kind + data) & 0xffffffff)
    rows = bytearray()
    for y in range(height):
        row = bytes(0 if pixel(frame, width, x, y) else 255 for x in range(width) for _ in range(scale))
        rows += (b'\0' + row) * scale
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width*scale, height*scale, 8, 0, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(bytes(rows))) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', type=Path, required=True)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    if args.preview_only and not args.preview_dir:
        parser.error('--preview-only requires --preview-dir')
    elf = Elf(args.resident_elf)
    elf.require_libm_math(args.resident_elf)
    with tempfile.TemporaryDirectory(prefix='mk61-focal-graphics-arm-') as directory:
        work = Path(directory); reader = work / 'reader'
        run(['c++', '-std=c++17', '-O2', '-I'+str(ROOT/'code'),
             ROOT/'tests/portable_app_format_self_test.cpp', ROOT/'code/loadable_module_format.cpp',
             ROOT/'code/zx0.cpp', '-o', reader])
        packages = {kind: package(reader, args.system/name, elf, work, kind, fixture_bytes=4096)
                    for kind, name in (('focal','FOCAL.APP'),('language-vm','LANGVM.APP'),('language-input','LANGIN.APP'))}
        def machine(address, width, height):
            value = OverlayMachine(args.resident_elf, True, address)
            value.pool_begin = (value.input + 4096 + 31) & ~31
            value.compiler_image_capacity = 2048
            value.graphics_dimensions = (width,height)
            value.legacy_rows = height//8
            value.call_timeout_us = 30_000_000
            return value
        # Graphics-aware FOCAL requires the resident protocol before callbacks.
        missing = machine(0,80,16)
        missing.service_capabilities_mask = 0xffffffff ^ (1 << 20)
        missing.kind, variants, missing.image_size, missing.entry, missing.crc = packages['focal']
        missing.base, missing.image = variants[0]
        missing.uc.mem_write(missing.pool_begin,b"\xCD"*(missing.pool_end-missing.pool_begin))
        missing.uc.mem_write(missing.base,missing.image)
        missing.uc.ctl_remove_cache(missing.pool_begin,missing.pool_end)
        assert missing.call(0,missing.api,missing.crc,1) != 0
        completed = []
        for address in (() if args.preview_only else range(3)):
            for width,height in ((80,16),(192,64)):
                def perform(source, answers=(), expected=0, cancelled=False):
                    value = machine(address,width,height)
                    result = execute(value,packages,2,source,list(answers),cancelled=cancelled)
                    assert result[1] == expected, (result,value.lines,value.trace[-12:])
                    return value,result
                value,result = perform(b'1.10 CLS; PSET 1,1; LINE 0,GH-1,GW-1,GH-1\n'
                    b'1.20 BOX 3,3,7,7,1,1; CIRCLE 20,8,3; PRINT AT 30,0,"A"; SHOW\n'
                    b'1.30 S A=GW+GH+POINT(1,1); EXIT\n')
                frame = value.frames[-1]
                assert result[0] == width+height+1
                assert len(frame) == width*height//8
                assert all(pixel(frame,width,x,y) for x,y in ((1,1),(4,4),(20,5),(width-1,height-1)))
                assert any(pixel(frame,width,x,y) for x in range(30,35) for y in range(8))
                assert not any(pixel(frame,width,35,y) for y in range(8))
                value,result = perform(b'1.10 S X=42; CLS; GRAPH X+0+0+0,-1,1,-1,1; S A=X; EXIT\n')
                assert result[0] == 42 and pixel(value.frames[-1],width,0,height-1) and pixel(value.frames[-1],width,width-1,0)
                value,result = perform(b'1.10 CLS; PSET GW-1,GH-1; ASK N; S A=N+POINT(GW-1,GH-1); EXIT\n',['7'])
                assert result[0] == 8 and len(value.frames)>=2 and pixel(value.frames[-1],width,width-1,height-1), (result,len(value.frames),value.lines,[pixel(f,width,width-1,height-1) for f in value.frames])
                value,result = perform(b'1.10 CLS; PRINT AT 2,0,%5.3,CALL(2),!,9; EXIT\n'
                    b'2.10 PRINT AT 50,8,"N"; RETURN 7\n')
                frame=value.frames[-1]
                assert not any(pixel(frame,width,x,y) for x in range(2,26) for y in range(8))
                assert any(pixel(frame,width,x,y) for x in range(26,31) for y in range(8))
                assert any(pixel(frame,width,x,y) for x in range(26,31) for y in range(8,16))
                assert any(pixel(frame,width,x,y) for x in range(50,55) for y in range(8,16))
                value,result = perform(b'1.10 S X=77; CLS; GRAPH 1/0,-1,1,-1,1; S A=X; EXIT\n')
                assert result[0] == 77
                completed.append({'relocation':address,'width':width,'height':height,'status':'PASS'})
                print(f'FOCAL ARM graphics: relocation {address}, {width}x{height} PASS',flush=True)
        if args.preview_dir:
            args.preview_dir.mkdir(parents=True,exist_ok=True)
            source=(ROOT/'programs/examples/Graphics.foc').read_bytes()
            for width,height in ((192,64),(80,16)):
                value=machine(0,width,height)
                value.call_timeout_us=180_000_000
                value.call_instruction_limit=100_000_000
                value.keys=[value.mapping[38]]*2
                result=flow_execute(value,packages,2,source,[])
                assert result[1] == 0,(result,value.lines)
                names=('primitives','graph') if height>16 else ('compact',)
                frames=[]
                for frame in value.frames:
                    if not frames or frame != frames[-1]: frames.append(frame)
                assert len(frames)==len(names),(width,height,len(frames))
                for name,frame in zip(names,frames):
                    (args.preview_dir/(name+'.bin')).write_bytes(frame)
                    png(args.preview_dir/(name+'.png'),frame,width,height)
                print(f'Graphics.foc: {width}x{height} preview PASS',flush=True)
            (args.preview_dir/'result.json').write_text(json.dumps({'status':'PREVIEW_PASS' if args.preview_only else 'PASS','cases':completed},indent=2)+'\n')
        if not args.preview_only:
            print('FOCAL graphics ARM: real compiler/raster/font, nested PRINT AT, GRAPH, 3 relocations, 80x16/192x64, INPUT eviction PASS')


if __name__ == '__main__':
    main()
