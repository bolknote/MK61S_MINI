#!/usr/bin/env python3
"""Execute reduced exact C output paths; qualify framing, CRC and old decoder."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / '.build/rp2040-interpolator-20261023/followon'
OUT = OLD / 'cdc-output'
sys.path[:0] = [str(HERE), str(ROOT / 'tests'), str(ROOT / 'tools')]
from verify import Model
from decode import decode
from build_picocalc import compiler_bin
from m0_math_compare_app_self_test import SHIM
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC


def load_parser():
    spec = importlib.util.spec_from_file_location('_cdc_result_test', HERE / 'cdc-result.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = load_parser()
    tc = compiler_bin(None)
    dest = OUT / 'protocol'
    dest.mkdir(exist_ok=True)
    shim = SHIM.replace('MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_FILE_WRITE,MK61_SERVICE_CAP_FILES',
                        'MK61_SERVICE_DEBUG_WRITE,0,MK61_SERVICE_CAP_DEBUG_IO')
    assert shim != SHIM
    (dest / 'api.c').write_text(shim)
    flags = ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-fno-builtin',
             '-ffunction-sections', '-fdata-sections', '-I' + str(HERE),
             '-I' + str(ROOT / 'sdk/portable/include'), '-I' + str(ROOT / 'code')]
    for name, source in [('api', dest / 'api.c'), ('memory', ROOT / 'sdk/portable/memory.c')]:
        subprocess.run([str(tc / 'arm-none-eabi-gcc'), *flags, '-c', str(source), '-o', str(dest / (name + '.o'))], check=True)
    report = dict(status='PASS', physical_timing=False, scope='Exact new C output path, reduced 4 samples / 2 rounds; unchanged arithmetic qualification reused', variants={})
    for ident, variant in enumerate(('lookup', 'pop', 'sqrt', 'rsqrt'), 1):
        obj, elf = dest / (variant + '.o'), dest / (variant + '.elf')
        subprocess.run([str(tc / 'arm-none-eabi-gcc'), *flags, '-DINTERP_VARIANT=' + str(ident),
                        '-DINTERP_SAMPLES=4', '-DINTERP_ROUNDS=2', '-c', str(HERE / 'benchmark-cdc.c'), '-o', str(obj)], check=True)
        objects = [obj, dest / 'api.o', dest / 'memory.o', *[OLD / (n + '.o') for n in ('lookup.cpp', 'pop.cpp', 'roots.cpp', 'sqrt-full.S', 'divide.S')]]
        subprocess.run([str(tc / 'arm-none-eabi-gcc'), *flags, '-nostdlib', *map(str, objects),
                        '-Wl,-T,' + str(OLD / 'kernels.ld'), '-Wl,-e,main', '-lgcc', '-o', str(elf)], check=True)
        m = Model(elf)
        m.instruction_budget = 100000000
        uc = m.uc
        for base in (0x40054000, 0x40008000, 0x40028000):
            uc.mem_map(base, 4096)
        initial = []
        for bank in range(2):
            for off, value in zip((0, 4, 8, 12, 16, 44, 48), (0x12345678 + bank, 0x89abcdef - bank, 123, 456, 789, 15 << 10, 31 << 10)):
                uc.mem_write(0xd0000080 + bank * 64 + off, struct.pack('<I', value))
                initial.append(value)
        uc.mem_write(0xd0000078, struct.pack('<I', 1))
        for addr, value in zip((0x4000803c, 0x40008040, 0x40008044, 0x40028000, 0x40028004, 0x40028008, 0x4002800c),
                               (1, 256, 2, 0x80000001, 4, 125, (6 << 16) | (2 << 12))):
            uc.mem_write(addr, struct.pack('<I', value))
        ticks, emitted = 0, []

        def timer(uc, access, address, size, value, user):
            nonlocal ticks
            ticks += 100
            uc.mem_write(address, struct.pack('<I', ticks))

        uc.hook_add(UC_HOOK_MEM_READ, timer, begin=0x40054028, end=0x4005402b)
        operations = struct.unpack('<4I', uc.mem_read(m.elf.symbols['operations'], 16))

        def callback(uc, address, size, user):
            regs = [uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            result = 0
            if address == 0x080e0020:
                result = m.elf.symbols['services']
            elif address == 0x080e0010:
                if regs[0] == operations[0]:
                    result = operations[3]
                else:
                    assert regs[0] == operations[1] and 0 < regs[1] <= 128 and regs[2:] == [0, 0], regs
                    ptr = int.from_bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 4), 'little')
                    line = bytes(uc.mem_read(ptr, regs[1]))
                    assert line.endswith(b'\n') and b'\0' not in line and line.isascii()
                    # Result output begins only after all peripheral state is restored.
                    restored = [int.from_bytes(uc.mem_read(0xd0000080 + bank * 64 + off, 4), 'little')
                                for bank in range(2) for off in (0, 4, 8, 12, 16, 44, 48)]
                    assert restored == initial
                    emitted.append(line)
                    result = 1
            else:
                assert address == 0x080e0050
            uc.reg_write(UC_ARM_REG_R0, result)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        for address in (0x080e0010, 0x080e0020, 0x080e0050):
            uc.mem_write(address, b'\x70\x47')
            uc.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)
        returned = m.call('main', 0)[0] & 0xffffffff
        assert returned == 0 and emitted
        # Frozen Pico stdio converts LF to CRLF; preserve exact C-generated text.
        raw = b'open "FLOOK.APP"\r\n' + b''.join(emitted).replace(b'\n', b'\r\n') + b'APP_RESULT=0\r\nAPP_FLOW_RESULT=0\r\nmk61> '
        payload = parser.parse(raw, variant, rounds=2)
        decoded = decode(payload, variant=variant, physical=False, expected_rounds=2, expected_samples=4)
        (dest / (variant + '-exchange.bin')).write_bytes(raw)
        (dest / (variant + '-RESULT.bin')).write_bytes(payload)
        lines = raw.split(b'\r\n')
        begin = next(i for i, line in enumerate(lines) if line.startswith(b'IFO4:B:'))
        data = begin + 1
        end = next(i for i, line in enumerate(lines) if line.startswith(b'IFO4:E:'))
        malformed = []
        for index, replacement in [(begin, b'IFO4:B:00000000:00000000'), (end, b'IFO4:E:00000000:00000000'),
                                   (data, lines[data].replace(b'00000000:', b'00000020:', 1)),
                                   (data, lines[data][:-2]), (data, b'UNKNOWN'), (data, lines[data] + b'00')]:
            altered = lines.copy()
            altered[index] = replacement
            malformed.append(b'\r\n'.join(altered))
        for index in (begin, data, end):
            altered = lines.copy()
            altered.insert(index, altered[index])
            malformed.append(b'\r\n'.join(altered))
        altered = lines.copy()
        altered[data] = altered[data][:-1] + (b'0' if altered[data][-1:] != b'0' else b'1')
        malformed.extend((b'\r\n'.join(altered), raw.replace(b'\r\nIFO4:E:', b'\nIFO4:E:'), raw + b'\0'))
        for bad in malformed:
            try:
                parser.parse(bad, variant, rounds=2)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Accepted malformed result exchange')
        report['variants'][variant] = dict(rows=decoded['rows'], result_bytes=len(payload),
                debug_calls=len(emitted), max_debug_bytes=max(map(len, emitted)), negative_frames=len(malformed),
                crc32=f'{zlib.crc32(payload):08X}', timer_reads=ticks // 100,
                elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())
        print('C output / strict framing / old decoder PASS ' + variant, flush=True)
    (OUT / 'protocol-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
