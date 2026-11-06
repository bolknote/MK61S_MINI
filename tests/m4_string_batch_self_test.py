#!/usr/bin/env python3
"""One grouped check of strnlen/strcpy/strncpy/strncat candidates.

--build-only compiles the complete package and records bodies without importing
or constructing Unicorn. The default additionally executes one deterministic
HOST semantic pass. Neither mode accesses hardware or measures device speed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage

FUNCTIONS = ('strnlen', 'strcpy', 'strncpy', 'strncat')
LENGTHS = (0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128, 255, 512)
FLASH = 0x08000000
RAM = 0x20000000
DEST_PAGE = RAM + 0x10000
SOURCE_RAM = RAM + 0x12000
SOURCE_FLASH = FLASH + 0x60000
PAGE_BYTES = 4096
CANARY = 0xa5


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def body(image, name):
    address = image.symbols[name] & ~1
    size = image.sizes[name]
    for kind, offset, va, _pa, count, _mem, _flags, _align in image.segments:
        if kind == 1 and va <= address and address + size <= va + count:
            return image.data[offset + address - va:offset + address - va + size]
    raise AssertionError(('function outside file-backed ELF segment', name))


def compile_package(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv):
        argv = list(map(str, argv))
        result = subprocess.run(argv, capture_output=True, text=True)
        commands.append(dict(argv=argv, EXIT=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        save(out / 'COMMANDS.json', commands)
        assert result.returncode == 0, result.stdout + result.stderr

    def flags(cpu):
        return ['-mcpu=' + cpu, '-mthumb', '-mfloat-abi=soft', '-Os',
                '-fno-builtin', '-fno-lto', '-ffunction-sections',
                '-fdata-sections', '-I' + str(ROOT / 'code'),
                '-I' + str(ROOT / 'sdk/portable/include')]

    cc = args.toolchain_bin.resolve() / 'arm-none-eabi-gcc'
    variants = [
        ('m4-byte2', 'cortex-m4', ['-DMK61_M4_STRING_BATCH_UNROLL=2']),
        ('m4-byte4', 'cortex-m4', ['-DMK61_M4_STRING_BATCH_UNROLL=4']),
        ('m4-control', 'cortex-m4', ['-DMK61_M4_STRING_BATCH_DISABLE=1']),
        ('f401', 'cortex-m4', ['-DSTM32F401xC']),
        ('f401-control', 'cortex-m4',
         ['-DSTM32F401xC', '-DMK61_M4_STRING_BATCH_DISABLE=1']),
        ('m0', 'cortex-m0plus', []),
        ('m0-control', 'cortex-m0plus', ['-DMK61_M4_STRING_BATCH_DISABLE=1']),
    ]
    images = {}
    products = []
    for name, cpu, extra in variants:
        path = out / (name + '.elf')
        run([cc, *flags(cpu), *extra, '-DMK61_STRING_TEST_BUILD=1',
             '-nostdlib', '-Wl,--gc-sections,--build-id=none,-e,strnlen',
             '-Wl,-Ttext=0x08002000', *['-Wl,-u,' + f for f in FUNCTIONS],
             ROOT / 'code/system_strings.c', '-lgcc', '-o', path])
        image = images[name] = ElfImage(path)
        functions = {}
        for function in FUNCTIONS:
            data = body(image, function)
            functions[function] = dict(entry=image.symbols[function],
                                      bytes=len(data),
                                      sha256=hashlib.sha256(data).hexdigest())
        products.append(dict(variant=name, cpu=cpu, ELF=pin(path),
                             functions=functions))

    pointer = out / 'runtime-pointer.c'
    pointer.write_text('#include <stdint.h>\nuintptr_t* mk61_app_runtime;\n')
    tail_path = out / 'runtime21.elf'
    run([cc, *flags('cortex-m4'),
         '-DMK61_RUNTIME_POINTER=mk61_app_runtime', '-nostdlib',
         '-Wl,--gc-sections,--build-id=none,-e,strncat',
         '-Wl,-Ttext=0x20006000,--section-start=.bss=0x20007000',
         ROOT / 'sdk/portable/system/runtime.S', pointer, '-o', tail_path])
    tail = ElfImage(tail_path)
    manifest = dict(status='COMPILED_GROUPED_VALIDATION_NOT_RUN',
                    physical_IO=0, semantic_execution=False,
                    hardware_timing=False, variants=products,
                    runtime=dict(ELF=pin(tail_path), count=26, slot=21,
                                 public_tail_bytes=tail.sizes['strncat']),
                    source=pin(Path(__file__)),
                    case_lengths=list(LENGTHS),
                    runtime_function='strncat',
                    no_runtime_slots_added=True,
                    source_pins=[pin(ROOT / path) for path in (
                        'code/system_strings.c',
                        'code/memory_strnlen_arm.h',
                        'code/memory_string_copy_arm.h',
                        'code/memory_strncat_arm.h',
                        'sdk/portable/system/runtime.S',
                        'code/loadable_system_runtime.def',
                        'tests/check_stm32_vectors.py')])
    save(out / 'BUILD.json', manifest)
    return images, tail, manifest


def nonzero(length):
    # Exercise both signed-char boundaries while reserving NUL as terminator.
    return bytes(1 + (128 + 37 * i) % 255 for i in range(length))


def cases(functions):
    """Nonoverlapping ISO C buffers; every copy alignment pair is explicit."""
    for length_index, length in enumerate(LENGTHS):
        for source_align in range(4):
            for destination_align in range(4):
                for source_bank in ('SRAM', 'Flash'):
                    for edge in ('head', 'tail'):
                        for function in functions:
                            # A read-only length function has one alignment,
                            # rather than four duplicate destination choices.
                            if function == 'strnlen' and destination_align:
                                continue
                            limits = [None] if function == 'strcpy' else sorted({
                                0, 1, max(0, length - 1), length,
                                length + 1, length + 7})
                            if function in ('strnlen', 'strncat'):
                                limits.append(0xffffffff)
                            prefix_length = LENGTHS[(length_index + 5) % len(LENGTHS)]
                            for limit in limits:
                                yield dict(function=function, length=length,
                                           source_align=source_align,
                                           destination_align=destination_align,
                                           source_bank=source_bank, edge=edge,
                                           count=limit, terminated=True,
                                           prefix_length=prefix_length)
                            if function != 'strcpy':
                                # Valid bounded, unterminated input, including
                                # a zero-byte object with n==0.
                                yield dict(function=function, length=length,
                                           source_align=source_align,
                                           destination_align=destination_align,
                                           source_bank=source_bank, edge=edge,
                                           count=length, terminated=False,
                                           prefix_length=prefix_length)


class Machine:
    def __init__(self, image, tail=None):
        # --build-only never imports native Unicorn or the runtime guard.
        from unicorn_runtime import Uc
        from unicorn import (UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB,
                             UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
        import unicorn.arm_const as arm
        self.arm = arm
        self.u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        self.u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M4)
        self.u.mem_map(FLASH, 0x80000)
        self.u.mem_map(RAM, 0x20000)
        image.load(self.u)
        self.image = image
        self.tail = tail
        images = [image]
        self.table = RAM + 0x8000
        self.stop = FLASH + 0x7ff00
        self.sp = RAM + 0x1fff0
        if tail is not None:
            tail.load(self.u)
            images.append(tail)
            self.u.mem_write(tail.symbols['mk61_app_runtime'],
                             struct.pack('<I', self.table))
            pointers = [self.stop | 1] * 26
            pointers[21] = image.symbols['strncat'] | 1
            self.u.mem_write(self.table, struct.pack('<26I', *pointers))
        self.code = [(va, va + count)
                     for e in images
                     for kind, _off, va, _pa, count, _mem, _flags, _a in e.segments
                     if kind == 1 and count]
        self.reads = []
        self.writes = []
        self.max_frame = 0
        self.calls = 0
        self.current = None

        def read(_u, _access, address, size, _value, _user):
            if any(lo <= address and address + size <= hi for lo, hi in self.code):
                return
            if self.sp - 512 <= address and address + size <= self.sp:
                self.max_frame = max(self.max_frame, self.sp - address)
                return
            if tail is not None and (
                    self.table <= address and address + size <= self.table + 104 or
                    tail.symbols['mk61_app_runtime'] <= address and
                    address + size <= tail.symbols['mk61_app_runtime'] + 4):
                return
            assert size == 1, ('input read must be a byte', self.current,
                               hex(address), size)
            assert any(lo <= address and address + size <= hi
                       for lo, hi in self.reads), ('input read envelope',
                                                 self.current, hex(address), size)

        def write(_u, _access, address, size, _value, _user):
            if self.sp - 512 <= address and address + size <= self.sp:
                self.max_frame = max(self.max_frame, self.sp - address)
                return
            assert size in (1, 2, 4), ('unexpected store size', self.current, size)
            if size > 1:
                assert address % size == 0, ('unaligned padding store',
                                             self.current, hex(address), size)
            assert any(lo <= address and address + size <= hi
                       for lo, hi in self.writes), ('destination write envelope',
                                                  self.current, hex(address), size)

        self.u.hook_add(UC_HOOK_MEM_READ, read)
        self.u.hook_add(UC_HOOK_MEM_WRITE, write)

    def invoke(self, function, r0, r1, r2=0):
        a = self.arm
        registers = [getattr(a, 'UC_ARM_REG_R' + str(i)) for i in range(4, 12)]
        saved = {r: 0xa1400000 + i * 0x101 for i, r in enumerate(registers)}
        for r, value in saved.items():
            self.u.reg_write(r, value)
        control = 0
        mask = self.calls & 1
        for r, value in [(a.UC_ARM_REG_R0, r0), (a.UC_ARM_REG_R1, r1),
                         (a.UC_ARM_REG_R2, r2), (a.UC_ARM_REG_SP, self.sp),
                         (a.UC_ARM_REG_LR, self.stop | 1),
                         (a.UC_ARM_REG_XPSR, 0x01000000),
                         (a.UC_ARM_REG_PRIMASK, mask),
                         (a.UC_ARM_REG_CONTROL, control)]:
            self.u.reg_write(r, value)
        address = (self.tail.symbols['strncat'] if self.tail is not None
                   else self.image.symbols[function])
        self.u.emu_start(address | 1, self.stop, count=100000)
        assert self.u.reg_read(a.UC_ARM_REG_PC) == self.stop, ('instruction cap', self.current)
        assert self.u.reg_read(a.UC_ARM_REG_SP) == self.sp, ('SP', self.current)
        assert all(self.u.reg_read(r) == value for r, value in saved.items()), ('AAPCS', self.current)
        assert self.u.reg_read(a.UC_ARM_REG_PRIMASK) == mask, ('PRIMASK', self.current)
        assert self.u.reg_read(a.UC_ARM_REG_CONTROL) == control, ('CONTROL', self.current)
        self.calls += 1
        return self.u.reg_read(a.UC_ARM_REG_R0)

    @staticmethod
    def pointer(page, count, alignment, edge):
        if edge == 'head':
            return page + 128 + alignment
        address = page + PAGE_BYTES - count
        return address - ((address - alignment) & 3)

    def check(self, case, candidate):
        self.current = case
        function = case['function']
        length, n = case['length'], case['count']
        source_data = nonzero(length) + (b'\0' if case['terminated'] else b'')
        consumed = (length + 1 if function == 'strcpy'
                    else min(n, length + int(case['terminated'])))
        source_page = SOURCE_RAM if case['source_bank'] == 'SRAM' else SOURCE_FLASH
        source = self.pointer(source_page, len(source_data), case['source_align'], case['edge'])
        source_image = bytearray([CANARY]) * PAGE_BYTES
        source_image[source - source_page:source - source_page + len(source_data)] = source_data
        self.u.mem_write(source_page, bytes(source_image))

        prefix = nonzero(case['prefix_length']) if function == 'strncat' else b''
        if function == 'strcpy':
            result = source_data
        elif function == 'strncpy':
            result = nonzero(length)[:n] + bytes(max(0, n - length))
        elif function == 'strncat':
            result = prefix + nonzero(length)[:n] + b'\0'
        else:
            result = b''
        destination = self.pointer(DEST_PAGE, len(result), case['destination_align'], case['edge'])
        destination_image = bytearray([CANARY]) * PAGE_BYTES
        if function == 'strncat':
            at = destination - DEST_PAGE
            destination_image[at:at + len(prefix) + 1] = prefix + b'\0'
        expected = bytearray(destination_image)
        if function != 'strnlen':
            at = destination - DEST_PAGE
            expected[at:at + len(result)] = result
        self.u.mem_write(DEST_PAGE, bytes(destination_image))
        self.reads = [(source, source + consumed)] if consumed else []
        self.writes = []
        if function == 'strncat':
            if n or not candidate:
                self.reads.append((destination, destination + len(prefix) + 1))
                self.writes.append((destination + len(prefix), destination + len(result)))
        elif function in ('strcpy', 'strncpy') and result:
            self.writes = [(destination, destination + len(result))]
        if function == 'strnlen':
            actual = self.invoke(function, source, n)
            assert actual == min(length, n), ('length result', case, actual)
        else:
            actual = self.invoke(function, destination, source, n or 0)
            assert actual == destination, ('return original destination', case, hex(actual))
        assert bytes(self.u.mem_read(source_page, PAGE_BYTES)) == source_image, ('source modified', case)
        assert bytes(self.u.mem_read(DEST_PAGE, PAGE_BYTES)) == expected, ('output/canary/prefix', case)

    def no_touch(self, function):
        self.current = dict(function=function, case='n0_unmapped_input_and_destination')
        self.reads = self.writes = []
        if function == 'strnlen':
            assert self.invoke(function, 0x60000000, 0) == 0
        else:
            assert self.invoke(function, 0x60001000, 0x60000000, 0) == 0x60001000


def execute(images, tail):
    for target in ('f401', 'm0'):
        for function in FUNCTIONS:
            assert body(images[target], function) == body(images[target + '-control'], function), (
                'fallback changed', target, function)
    assert tail.sizes['strncat'] == 12, 'unchanged M4 SDK tail required'
    results = []
    for variant in ('m4-control', 'm4-byte2', 'm4-byte4'):
        for shared in (False, True):
            machine = Machine(images[variant], tail if shared else None)
            functions = ('strncat',) if shared else FUNCTIONS
            counters = Counter()
            for case in cases(functions):
                try:
                    machine.check(case, candidate=variant != 'm4-control')
                except BaseException as error:
                    raise AssertionError(dict(variant=variant, shared=shared,
                                              first_case=case,
                                              first_error=repr(error))) from error
                counters[case['function']] += 1
            # The old C strncat legitimately searches/writes its valid
            # destination for n==0. Do not impose the new extra guarantee on it.
            extras = ('strncat',) if shared else ('strnlen', 'strncpy', 'strncat')
            for function in extras:
                if function == 'strncat' and variant == 'm4-control':
                    continue
                try:
                    machine.no_touch(function)
                except BaseException as error:
                    raise AssertionError(dict(variant=variant, shared=shared,
                                              first_case=machine.current,
                                              first_error=repr(error))) from error
                counters[function] += 1
            results.append(dict(variant=variant,
                                route='real-runtime26-slot21' if shared else 'native',
                                calls=machine.calls, functions=dict(counters),
                                maximum_stack_frame=machine.max_frame))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-only', action='store_true',
                        help='compile all variants without semantic execution')
    args = parser.parse_args()
    images, tail, manifest = compile_package(args)
    if args.build_only:
        print(json.dumps(pin(args.output.resolve() / 'BUILD.json')))
        return
    try:
        results = execute(images, tail)
    except BaseException as error:
        save(args.output / 'FIRST-FAILURE.json', dict(status='FIRST_FAILURE_NO_RETRY',
                                                    error=repr(error), physical_IO=0))
        raise
    result = dict(status='PASS_GROUPED_HOST_SEMANTICS_ONLY_HARDWARE_NOT_RUN',
                  build=pin(args.output / 'BUILD.json'), physical_IO=0,
                  hardware_timing=False, results=results,
                  fallback_F401_M0_identical_to_disabled_controls=True,
                  runtime_count=26, strncat_runtime_slot=21,
                  source=pin(Path(__file__)))
    save(args.output / 'RESULT.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
