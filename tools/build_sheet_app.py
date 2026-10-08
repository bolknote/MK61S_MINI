#!/usr/bin/env python3
"""Build SHEET.APP and ready-to-open S1/.mks demonstration documents."""
import argparse
import binascii
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def document(cells, angle=0, compact=0):
    payload = bytearray()
    for address, kind, source in cells:
        column = ord(address[0])-ord('A')
        row = int(address[1:])-1
        encoded = source.encode('cp1251' if kind == 2 else 'ascii')
        if not (0 <= column < 16 and 0 <= row < 32 and 0 < len(encoded) < 96):
            raise ValueError('invalid example cell')
        payload += struct.pack('<HBB', row*16+column, kind, len(encoded)) + encoded
    if len(cells) > 64 or sum(len(s.encode('cp1251')) for _, _, s in cells) > 1536:
        raise ValueError('example exceeds document budget')
    header = bytearray(20)
    header[:4] = b'MKSH'
    header[4:10] = bytes((1,16,32,angle,compact,len(cells)))
    struct.pack_into('<H', header, 12, len(payload))
    struct.pack_into('<I', header, 16, binascii.crc32(header[:16]+payload))
    return header + payload


def examples(destination):
    destination.mkdir(parents=True, exist_ok=True)
    cells = [('A1',2,'КОЛ-ВО'),('B1',2,'ЦЕНА'),('C1',2,'СУММА'),('D1',2,'НАЛОГ')]
    for row, quantity, price in ((2,2,125),(3,3,80),(4,1,350)):
        cells += [(f'A{row}',1,str(quantity)), (f'B{row}',1,str(price)),
                  (f'C{row}',3,f'A{row} ENT B{row} *'), (f'D{row}',3,f'C{row} ENT 0.2 *')]
    cells += [('B5',2,'ИТОГО'),('C5',3,'C2 ENT C3 + C4 +'),('D5',3,'D2 ENT D3 + D4 +')]
    (destination/'BUDGET.mks').write_bytes(document(cells))
    (destination/'CYCLE.mks').write_bytes(document([('A1',3,'B1'),('B1',3,'A1'),('C1',1,'42')]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'.build/portable-apps/sheet')
    parser.add_argument('--copy-to-programs',action='store_true',help='copy the built APP and examples into the local programs tree')
    args = parser.parse_args()
    toolchain = args.arm_toolchain_bin
    if toolchain is None:
        gcc = shutil.which('arm-none-eabi-gcc')
        candidates = list((Path.home()/'Library/Arduino15/packages/STMicroelectronics/tools').glob('xpack-arm-none-eabi-gcc/*/bin/arm-none-eabi-gcc'))
        if gcc:
            toolchain = Path(gcc).parent
        elif candidates:
            toolchain = sorted(candidates)[-1].parent
        else:
            parser.error('specify --arm-toolchain-bin or put ARM GCC on PATH')
    command = [sys.executable,str(ROOT/'tools/build_portable_app.py'),'--name','SHEET',
               '--source',str(ROOT/'examples/portable-apps/SHEET/main.cpp'),
               '--source',str(ROOT/'examples/portable-apps/SHEET/sheet_engine.cpp'),
               '--shared-runtime','--handled-magic','S1','--arm-toolchain-bin',str(toolchain),
               '--output-dir',str(args.output_dir)]
    subprocess.run(command,check=True)
    report = json.loads((args.output_dir/'SHEET.json').read_text())
    if report['memory_bytes'] > 20480:
        raise ValueError('SHEET exceeds the APP allocation')
    examples(args.output_dir/'sheets')
    if args.copy_to_programs:
        target = ROOT/'programs/app'
        target.mkdir(parents=True,exist_ok=True)
        shutil.copy2(args.output_dir/'SHEET.APP',target/'SHEET.APP')
        shutil.copy2(args.output_dir/'SHEET.json',target/'SHEET.json')
        examples(ROOT/'programs/sheets')
    print(f'SHEET.APP ready: {report["app_bytes"]} bytes on disk, {report["memory_bytes"]} bytes loaded')


if __name__ == '__main__':
    main()
