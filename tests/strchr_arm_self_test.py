#!/usr/bin/env python3
"""Build real ARM strchr baselines/candidates and execute strict memory/AAPCS tests.

No device access. Unicorn checks ARMv6-M/M4 behavior, never physical speed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/strchr-2026-10-28'
sys.path.insert(0, str(ROOT / 'tools'))
from check_stm32_vectors import ElfImage

VARIANTS = ['byte1', 'byte4', 'word1', 'word2', 'dsp1', 'dsp2']


def pin(path):
    blob = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())


def command(argv, log):
    argv = [str(x) for x in argv]
    p = subprocess.run(argv, capture_output=True, text=True)
    log.append(dict(argv=argv, exit=p.returncode, stdout=p.stdout, stderr=p.stderr))
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout


def build(tc, out):
    out.mkdir(parents=True, exist_ok=False)
    logs, products = [], []
    (out / 'runtime-pointer.c').write_text('#include <stdint.h>\nuintptr_t* mk61_app_runtime;\n')
    for arch, cpu in [('m4', 'cortex-m4'), ('m0', 'cortex-m0plus')]:
        flags = ['-mcpu=' + cpu, '-mthumb', '-mfloat-abi=soft', '-Os', '-fno-lto',
                 '-fno-builtin', '-fno-ipa-icf', '-fno-tree-loop-distribute-patterns',
                 '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
                 '-I' + str(ROOT / 'code'), '-I' + str(ROOT / 'sdk/portable')]
        objects = []
        sources = [('candidates', RESEARCH / 'candidates.S', []),
                   ('sdk', ROOT / 'sdk/portable/memory.c', ['-Dstrchr=sdk_strchr'])]
        if arch == 'm4':
            sources += [('native', ROOT / 'code/system_strings.c',
                         ['-DMK61_STRING_TEST_BUILD=1', '-Dstrchr=native_strchr'])]
        else:
            # Pico presently supplies no strchr override: future native baseline
            # must be rebound to the toolchain/body of the actually installed FW.
            sources += [('pico', ROOT / 'ports/picocalc/memory.c', ['-DPICO_ON_DEVICE=1'])]
        for name, source, defines in sources:
            obj = out / f'{arch}-{name}.o'
            command([tc / 'arm-none-eabi-gcc', *flags, *defines, '-c', source, '-o', obj], logs)
            if name in ['sdk', 'native']:
                # Isolate the retained real public body without changing its
                # instructions or allowing unrelated libc duplicates at link.
                command([tc / 'arm-none-eabi-objcopy', '--keep-global-symbol=' +
                         ('sdk_strchr' if name == 'sdk' else 'native_strchr'), obj], logs)
            if name != 'pico':
                objects.append(obj)
            else:
                names = command([tc / 'arm-none-eabi-nm', '--defined-only', obj], logs)
                assert not any(x.split()[-1] in ('strchr', '__wrap_strchr') for x in names.splitlines())
        names = [v + '_strchr' for v in VARIANTS[:6 if arch == 'm4' else 4]]
        names += ['sdk_strchr', 'strchr'] + (['native_strchr'] if arch == 'm4' else [])
        flash = 0x08000000 if arch == 'm4' else 0x10000000
        for placement, address in [('flash', flash + 0x2000), ('sram', 0x20002000)]:
            elf = out / f'{arch}-{placement}.elf'
            roots = [x for name in names for x in ['-Wl,-u,' + name]]
            command([tc / 'arm-none-eabi-gcc', *flags, '-nostdlib',
                     '-Wl,--build-id=none,--gc-sections', '-Wl,-e,byte1_strchr',
                     '-Wl,-Ttext=' + hex(address), *roots, *objects, '-lc', '-lgcc', '-o', elf], logs)
            image = ElfImage(elf)
            bodies = {}
            for name in names:
                addr, size = image.symbols[name] & ~1, image.sizes[name]
                body = next(image.data[off + addr - va:off + addr - va + size]
                            for kind, off, va, pa, n, mem, f, al in image.segments
                            if kind == 1 and va <= addr and addr + size <= va + n)
                bodies[name] = dict(bytes=size, sha256=hashlib.sha256(body).hexdigest(), address=addr)
            dis = command([tc / 'arm-none-eabi-objdump', '-d', elf], logs)
            (out / f'{arch}-{placement}.dis').write_text(dis)
            products.append(dict(arch=arch, placement=placement, elf=pin(elf), bodies=bodies))
        # The production SDK slot-18 tail, with the production runtime table order.
        objs = []
        for name, source in [('tails', ROOT / 'sdk/portable/system/runtime.S'),
                             ('pointer', out / 'runtime-pointer.c')]:
            obj = out / f'{arch}-{name}.o'
            command([tc / 'arm-none-eabi-gcc', *flags, '-DMK61_RUNTIME_POINTER=mk61_app_runtime',
                     '-c', source, '-o', obj], logs)
            objs.append(obj)
        elf = out / f'{arch}-runtime.elf'
        command([tc / 'arm-none-eabi-gcc', *flags, '-nostdlib',
                 '-Wl,--build-id=none,--gc-sections', '-Wl,-e,strchr', '-Wl,-Ttext=0x20006000',
                 '-Wl,--section-start=.bss=0x20007000', *objs, '-o', elf], logs)
        products.append(dict(arch=arch, placement='runtime', elf=pin(elf)))
    result = dict(products=products, commands=logs, physical_IO=0,
                  source_pins=[pin(ROOT / x) for x in ['code/system_strings.c', 'sdk/portable/memory.c',
                      'ports/picocalc/memory.c', 'sdk/portable/system/runtime.S',
                      'code/loadable_system_runtime.def', 'research/strchr-2026-10-28/candidates.S']])
    (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def corpus(random_cases):
    rng = random.Random(0x53544348)
    lengths = [*range(17), 31, 32, 33, 63, 64, 65, 127, 128, 129, 255, 256, 511, 1023]
    for n in lengths:
        for align in range(4):
            for edge in [0, 1]:
                for bank in ['sram', 'flash']:
                    for mode in ['nul', 'missing', 'first', 'middle', 'last', 'repeated', 'high', 'truncate', 'negative']:
                        blob = bytearray(b'\x81' * n)
                        c = {'nul': 0, 'missing': 0x52, 'first': 0x52, 'middle': 0x52,
                             'last': 0x52, 'repeated': 0x52, 'high': 255, 'truncate': 0x152,
                             'negative': -1}[mode]
                        if n and mode not in ('nul', 'missing'):
                            at = 0 if mode == 'first' else n // 2 if mode in ('middle', 'repeated', 'truncate', 'negative') else n - 1
                            blob[at] = c & 255
                            if mode == 'repeated':
                                blob[-1] = c & 255
                        yield dict(blob=bytes(blob), c=c, align=align, edge=edge, bank=bank, mode=mode)
    # Exhaust all byte values at all positions of one NUL-containing word.
    # This includes borrow propagation/high-bit traps in arithmetic zero masks.
    for c in range(256):
        for nul in range(8):
            for hit in range(nul + 1):
                blob = bytearray(b'\xff' * nul)
                if hit < nul and c:
                    blob[hit] = c
                yield dict(blob=bytes(blob), c=c, align=(c + nul) % 4, edge=c % 2,
                           bank='sram' if hit % 2 else 'flash', mode='exhaustive-lanes')
    for i in range(random_cases):
        blob = bytes(rng.randrange(1, 256) for _ in range(rng.randrange(1024)))
        c = rng.choice([rng.randrange(-0x80000000, 0x80000000), 0x100, -256, -1, 0x7fffffff, -0x80000000])
        yield dict(blob=blob, c=c, align=i % 4, edge=i % 2,
                   bank='sram' if i % 3 else 'flash', mode='random')


def run(build_result, out, random_cases):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
    from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
        UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR,
        UC_ARM_REG_PRIMASK, UC_ARM_REG_CONTROL)
    saved_regs = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                  UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
    cases = list(corpus(random_cases))
    results = []
    for arch in ['m4', 'm0']:
        flash = 0x08000000 if arch == 'm4' else 0x10000000
        native = ElfImage(out / f'{arch}-flash.elf')
        names = [v + '_strchr' for v in VARIANTS[:6 if arch == 'm4' else 4]]
        names += ['sdk_strchr', 'strchr'] + (['native_strchr'] if arch == 'm4' else [])
        for placement in ['flash', 'sram', 'runtime']:
            elf = ElfImage(out / f'{arch}-{placement}.elf')
            u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
            u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if arch == 'm4' else UC_CPU_ARM_CORTEX_M0)
            # Holes immediately before and after input pages remain unmapped.
            u.mem_map(flash, 0x10000)
            u.mem_map(0x20000000, 0x8000)
            u.mem_map(0x2001e000, 0x2000)
            for page in [0x20010000, flash + 0x60000]:
                u.mem_map(page, 4096)
            elf.load(u)
            images = [elf]
            if placement == 'runtime':
                native.load(u)
                images.append(native)
            code = [(va, va + n) for image in images
                    for kind, off, va, pa, n, mem, flags, al in image.segments
                    if kind == 1 and n and flags & 1]
            sp = 0x2001fff0
            stop = flash + 0xf000
            table = 0x2001e000
            active, counts, forwarded = {}, {}, []
            max_frame = 0

            def read(uc, access, address, n, value, user):
                nonlocal max_frame
                del uc, access, value, user
                if any(lo <= address and address + n <= hi for lo, hi in code):
                    return
                if sp - 64 <= address and address + n <= sp:
                    max_frame = max(max_frame, sp - address)
                    return
                if placement == 'runtime' and (table <= address and address + n <= table + 104 or
                    elf.symbols['mk61_app_runtime'] <= address and address + n <= elf.symbols['mk61_app_runtime'] + 4):
                    return
                assert active['pointer'] <= address and address + n <= active['end'], ('read envelope', arch, placement, active, hex(address), n)
                if n >= 4:
                    assert address % 4 == 0, ('unaligned word', hex(address), n)
                active['reads'] += 1

            def write(uc, access, address, n, value, user):
                nonlocal max_frame
                del uc, access, value, user
                assert sp - 64 <= address and address + n <= sp, ('input/non-frame write', hex(address), n)
                max_frame = max(max_frame, sp - address)

            u.hook_add(UC_HOOK_MEM_READ, read)
            u.hook_add(UC_HOOK_MEM_WRITE, write)
            if placement == 'runtime':
                u.mem_write(elf.symbols['mk61_app_runtime'], struct.pack('<I', table))

                def target_hook(uc, address, n, user):
                    del address, n, user
                    forwarded.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))

                for name in names:
                    addr = native.symbols[name] & ~1
                    u.hook_add(UC_HOOK_CODE, target_hook, begin=addr, end=addr)
            for index, c in enumerate(cases):
                page = 0x20010000 if c['bank'] == 'sram' else flash + 0x60000
                blob = c['blob'] + b'\0'
                pointer = page + c['align'] if not c['edge'] else page + 4096 - len(blob) - ((4096 - len(blob) - c['align']) & 3)
                # Put matches/NULs immediately outside the logical input too.
                # They must never win over the first in-string hit or NUL.
                data = bytearray(bytes([c['c'] & 255]) * 4096)
                at = pointer - page
                data[at:at + len(blob)] = blob
                u.mem_write(page, bytes(data))
                found = blob.find(bytes([c['c'] & 255]))
                expected = pointer + found if found >= 0 else 0
                for name in names:
                    byte = name.startswith(('byte', 'sdk_', 'native_'))
                    # Newlib has its own word-search implementation. Enforce
                    # the same no-prefix, containing-word ceiling here.
                    decisive_end = pointer + (found + 1 if found >= 0 else len(blob))
                    end = decisive_end if byte else (decisive_end + 3) & ~3
                    active.update(pointer=pointer, end=end, name=name, case=index, reads=0)
                    saved = {r: 0xa1730000 + i * 0x1011 for i, r in enumerate(saved_regs)}
                    for r, v in saved.items():
                        u.reg_write(r, v)
                    mask = index & 1
                    for r, v in [(UC_ARM_REG_R0, pointer), (UC_ARM_REG_R1, c['c'] & 0xffffffff),
                        (UC_ARM_REG_R2, 0x72727272), (UC_ARM_REG_R3, 0x83838383),
                        (UC_ARM_REG_SP, sp), (UC_ARM_REG_LR, stop | 1), (UC_ARM_REG_XPSR, 0x01000000),
                        (UC_ARM_REG_PRIMASK, mask), (UC_ARM_REG_CONTROL, 0)]:
                        u.reg_write(r, v)
                    before = len(forwarded)
                    if placement == 'runtime':
                        slots = [stop | 1] * 26
                        slots[18] = native.symbols[name] | 1
                        u.mem_write(table, struct.pack('<26I', *slots))
                    entry = elf.symbols['strchr' if placement == 'runtime' else name]
                    u.emu_start(entry | 1, stop, count=100000)
                    assert u.reg_read(UC_ARM_REG_PC) == stop, ('did not return', arch, placement, name, c)
                    assert u.reg_read(UC_ARM_REG_R0) == expected, ('result', arch, placement, name, c, expected, u.reg_read(UC_ARM_REG_R0))
                    assert u.reg_read(UC_ARM_REG_SP) == sp and all(u.reg_read(r) == v for r, v in saved.items()), ('AAPCS', name)
                    assert u.reg_read(UC_ARM_REG_PRIMASK) == mask and u.reg_read(UC_ARM_REG_CONTROL) == 0
                    if placement == 'runtime':
                        assert len(forwarded) == before + 1 and forwarded[-1] == (pointer, c['c'] & 0xffffffff), ('slot18/argument', name)
                    assert active['reads'] > 0
                    counts[name] = counts.get(name, 0) + 1
                assert bytes(u.mem_read(page, 4096)) == bytes(data), 'input/guards changed'
            # Qualify the guard hooks themselves using deliberately invalid
            # ARM loads/stores in otherwise mapped memory. None is a candidate.
            probe = flash + 0xe000
            pointer = 0x20010004
            active.update(pointer=pointer, end=pointer + 1, name='negative-guard-probe', reads=0)
            negative = 0
            for instructions in [(0x6842, 0x4770),       # ldr r2,[r0,#4]
                                 (0x3801, 0x7802, 0x4770),  # --r0; ldrb r2,[r0]
                                 (0x7001, 0x4770)]:      # strb r1,[r0]
                u.mem_write(probe, struct.pack('<' + 'H' * len(instructions), *instructions))
                u.ctl_remove_cache(probe, probe + 16)
                for r, v in [(UC_ARM_REG_R0, pointer), (UC_ARM_REG_R1, 0x55),
                             (UC_ARM_REG_SP, sp), (UC_ARM_REG_LR, stop | 1),
                             (UC_ARM_REG_XPSR, 0x01000000)]:
                    u.reg_write(r, v)
                try:
                    u.emu_start(probe | 1, stop, count=20)
                except AssertionError:
                    negative += 1
                else:
                    raise AssertionError('broken memory guard did not reject ARM probe')
            row = dict(arch=arch, placement=placement, cases=len(cases), counts=counts,
                       calls=sum(counts.values()), runtime18_forwards=len(forwarded), max_stack_bytes=max_frame,
                       inputs_and_guards_unchanged=True, AAPCS_SP_PRIMASK_CONTROL=True,
                       leading_and_trailing_unmapped_pages=True, rejected_invalid_ARM_read_write_probes=negative)
            results.append(row)
            print(arch, placement, row['calls'], 'strchr calls PASS', flush=True)
    # Literal relocation may change addresses, not code bodies, across banks.
    for arch in ['m4', 'm0']:
        a, b = [next(p for p in build_result['products'] if p['arch'] == arch and p['placement'] == bank)
                for bank in ['flash', 'sram']]
        for name in a['bodies']:
            assert a['bodies'][name]['sha256'] == b['bodies'][name]['sha256'], (arch, name, 'bank body drift')
    result = dict(status='PASS_HOST_ARM_STRCHR_NOT_HARDWARE_TIMING', physical_IO=0,
                  hardware_winner=None, results=results, total_calls=sum(r['calls'] for r in results),
                  candidate_read_envelope='byte exact, or aligned containing 4-byte NUL word, no prefix; each word checked before next',
                  M0_native='current GCC newlib surrogate only; installed body not yet bound')
    (out / 'RESULTS.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--random-cases', type=int, default=256)
    p.add_argument('--build-only', action='store_true')
    p.add_argument('--run-existing', action='store_true')
    a = p.parse_args()
    data = json.loads((a.output_dir / 'build.json').read_text()) if a.run_existing else build(a.toolchain_bin, a.output_dir)
    if not a.build_only:
        run(data, a.output_dir, a.random_cases)


if __name__ == '__main__':
    main()
