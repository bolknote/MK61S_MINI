#!/usr/bin/env python3
"""Real packed SDK APPs: strchr candidates, production runtime18, relocation/entry.

Only service query/capability discovery is modeled. SDK startup, binding,
runtime tails, local and resident ARM bodies execute. No device or timing.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tools'), str(ROOT / 'tools/.mk61-app')]
from check_stm32_vectors import ElfImage
from strchr_arm_self_test import pin, command, RESEARCH, VARIANTS


def build(tc, out, core):
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('strchr_app_builder', ROOT / 'tools/build_portable_app.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    normal_run = builder.run
    core_build = json.loads((core / 'build.json').read_text())
    apps = []
    for arch, target, limit in [('m4', 'stm32', 6), ('m0', 'picocalc-pico-h', 4)]:
        baseline = next(p for p in core_build['products'] if p['arch'] == arch and p['placement'] == 'sram')
        for route, variants in [('standalone', [0, *range(1, limit + 1), 7]), ('shared', [0])]:
            for variant in variants:
                folder = out / f'{arch}-{route}-v{variant}'
                actual = []

                def run(argv):
                    argv = [str(x) for x in argv]
                    if '-c' in argv:
                        if variant and str(ROOT / 'sdk/portable/memory.c') in argv:
                            argv += ['-Dstrchr=unused_sdk_strchr']
                        if str(RESEARCH / 'candidates.S') in argv:
                            argv += [f'-DST_VARIANT={variant}']
                        if str(RESEARCH / 'bench.c') in argv:
                            argv += ['-fno-lto']
                    actual.append(argv)
                    return normal_run(argv)

                builder.run = run
                sources = [RESEARCH / 'APP-CHECK.c', RESEARCH / 'bench.c'] + ([RESEARCH / 'candidates.S'] if variant in range(1, 7) else [])
                args = argparse.Namespace(target=target, name='STCHECK', source=sources, system=None,
                    shared_runtime=route == 'shared', text_only=False, no_ui_fonts=False,
                    local_float_math=False, local_float_math_mask=None, language_vm_compiler=False,
                    split_language_vm=False, include=[], library=[Path('-lc')] if variant == 7 else [],
                    output_dir=folder, arm_toolchain_bin=tc, packer=ROOT / 'tools/.mk61-app/mk61_module_pack.py',
                    rustc=None, handled_magic=None)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    report = builder.build(args)
                (folder / 'build.log').write_text(output.getvalue())
                (folder / 'actual-commands.json').write_text(json.dumps(actual, indent=2) + '\n')
                image = ElfImage(folder / 'STCHECK.elf')
                addr, size = image.symbols['strchr'] & ~1, image.sizes['strchr']
                body = next(image.data[off + addr - va:off + addr - va + size]
                            for kind, off, va, pa, n, mem, flags, al in image.segments
                            if kind == 1 and va <= addr and addr + size <= va + n)
                import hashlib
                digest = hashlib.sha256(body).hexdigest()
                if 1 <= variant <= 6:
                    assert digest == baseline['bodies'][VARIANTS[variant - 1] + '_strchr']['sha256'], ('candidate drift', arch, variant)
                apps.append(dict(arch=arch, route=route, variant=variant, APP=pin(folder / 'STCHECK.APP'),
                    ELF=pin(folder / 'STCHECK.elf'), report=report, actual_commands=pin(folder / 'actual-commands.json'),
                    strchr_bytes=size, strchr_sha256=digest))
                print(arch, route, variant, report['app_bytes'], 'APP bytes', report['memory_bytes'], 'RAM bytes', flush=True)
    builder.run = normal_run
    result = dict(apps=apps, physical_IO=0, runtime_count=26, strchr_slot=18,
                  source_pins=[pin(ROOT / x) for x in ['sdk/portable/start.c', 'sdk/portable/shared_runtime.c',
                      'sdk/portable/system/runtime.S', 'sdk/portable/memory.c', 'tools/build_portable_app.py',
                      'research/strchr-2026-10-28/APP-CHECK.c', 'research/strchr-2026-10-28/candidates.S',
                      'research/strchr-2026-10-28/bench.c', 'research/strchr-2026-10-28/bench.h']])
    (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def execute(data, core, out):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE
    from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
        UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR,
        UC_ARM_REG_PRIMASK, UC_ARM_REG_CONTROL)
    saved_regs = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                  UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
    readers, logs, results = {}, [], []
    for arch in ['m4', 'm0']:
        reader = out / ('decode-app-' + arch)
        command(['c++', '-std=c++17', '-O2', *(['-DMK61_CORE_STANDALONE=1'] if arch == 'm0' else []),
                 '-I' + str(ROOT / 'code'), ROOT / 'tests/portable_app_format_self_test.cpp',
                 ROOT / 'code/loadable_module_format.cpp', ROOT / 'code/zx0.cpp', '-o', reader], logs)
        readers[arch] = pin(reader)
    for app in data['apps']:
        arch = app['arch']
        flash = 0x08000000 if arch == 'm4' else 0x10000000
        resident = ElfImage(core / (arch + '-flash.elf'))
        elf = ElfImage(Path(app['ELF']['path']))
        packed = Path(app['APP']['path']).read_bytes()
        image_bytes, memory_bytes, entry = struct.unpack_from('<III', packed, 28)
        crc = struct.unpack_from('<I', packed, 52)[0]
        origin = app['report']['load_address']
        checks = runs = inits = negative = forwarded = bench_runs = bench_search_calls = 0
        backends = [v + '_strchr' for v in VARIANTS[:6 if arch == 'm4' else 4]]
        backends += ['sdk_strchr', 'strchr'] + (['native_strchr'] if arch == 'm4' else [])
        for base in [0x20002000, 0x20006000, 0x2000a000]:
            decoded = out / f"{arch}-{app['route']}-v{app['variant']}-{base:x}.decoded"
            command([readers[arch]['path'], app['APP']['path'], decoded, hex(base)], logs)
            blob = decoded.read_bytes()
            assert len(blob) == memory_bytes and memory_bytes <= 20480
            u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
            u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4 if arch == 'm4' else UC_CPU_ARM_CORTEX_M0)
            u.mem_map(flash, 0x100000)
            u.mem_map(0x20000000, 0x20000)
            resident.load(u)
            u.mem_write(base, blob)
            stop, api, services = flash + 0xff000, flash + 0xf1000, flash + 0xf2000
            table, query, caps, wrong = flash + 0xf2100, flash + 0xf2200, flash + 0xf2210, flash + 0xf2220
            fixture, sp = flash + 0x60000, 0x2001fff0
            fixture_blob = b'\xffA\x80A\0Z\xff\0' + b'\xa5' * 24
            u.mem_write(fixture, fixture_blob)

            def stub(address, value):
                u.mem_write(address, struct.pack('<HHI', 0x4800, 0x4770, value))

            stub(query, services)
            stub(caps, 256)
            stub(wrong, 0)
            synthetic_tick = flash + 0xf2230
            counter = 0x2001d000
            # ARM tick fixture: load/increment/store one counter and return it.
            # Synthetic fixed intervals exercise APP wiring, never MCU speed.
            u.mem_write(synthetic_tick, struct.pack('<6HI', 0x4b02, 0x6818, 0x3011, 0x6018, 0x4770, 0xbf00, counter))
            u.mem_write(api, struct.pack('<IHHI', 0x31505041, 1, 108, 0) + struct.pack('<24I', *([stop | 1] * 23 + [query | 1])))
            u.mem_write(services, struct.pack('<IHH5I', 0x31535953, 2, 28, 0, caps | 1, 0, 0, table))
            queries, target_calls = [], [0]

            def query_hook(uc, address, n, user):
                del address, n, user
                queries.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
                assert queries[-1] == (1, 2)

            u.hook_add(UC_HOOK_CODE, query_hook, begin=query, end=query)

            def target_hook(uc, address, n, user):
                del uc, address, n, user
                target_calls[0] += 1

            for name in backends:
                addr = resident.symbols[name] & ~1
                u.hook_add(UC_HOOK_CODE, target_hook, begin=addr, end=addr)

            def bind(name):
                slots = [stop | 1] * 26
                slots[18] = resident.symbols[name] | 1
                u.mem_write(table, struct.pack('<26I', *slots))

            def invoke(command_id):
                saved = {r: 0xa1740000 + i * 0x1011 for i, r in enumerate(saved_regs)}
                for r, v in saved.items():
                    u.reg_write(r, v)
                for r, v in [(UC_ARM_REG_R0, command_id), (UC_ARM_REG_R1, api), (UC_ARM_REG_R2, crc),
                    (UC_ARM_REG_R3, packed[12]), (UC_ARM_REG_SP, sp), (UC_ARM_REG_LR, stop | 1),
                    (UC_ARM_REG_XPSR, 0x01000000), (UC_ARM_REG_PRIMASK, 0), (UC_ARM_REG_CONTROL, 0)]:
                    u.reg_write(r, v)
                u.mem_write(sp, bytes(4))
                u.emu_start((base + entry) | 1, stop, count=10000000)
                assert u.reg_read(UC_ARM_REG_PC) == stop and u.reg_read(UC_ARM_REG_SP) == sp
                assert all(u.reg_read(r) == v for r, v in saved.items()), ('AAPCS', app, base)
                assert u.reg_read(UC_ARM_REG_PRIMASK) == 0 and u.reg_read(UC_ARM_REG_CONTROL) == 0
                return u.reg_read(UC_ARM_REG_R0)

            bind('sdk_strchr')
            if app['route'] == 'shared':
                u.mem_write(table + 18 * 4, bytes(4))
                assert invoke(0) == 5
                negative += 1
                bind('sdk_strchr')
            assert invoke(0) == 0
            inits += 1
            u.mem_write(base + elf.symbols['external_text'] - origin, struct.pack('<I', fixture))
            for backend in backends if app['route'] == 'shared' else ['sdk_strchr']:
                bind(backend)
                before = target_calls[0]
                assert invoke(1) == 0, ('APP result', app, base, backend)
                count = struct.unpack('<I', u.mem_read(base + elf.symbols['checks'] - origin, 4))[0]
                assert count == 576
                expected = 576 if app['route'] == 'shared' else 0
                assert target_calls[0] - before == expected, ('runtime route', app, backend)
                checks += count
                runs += 1
                forwarded += expected
                def symbol(name):
                    return base + elf.symbols[name] - origin
                u.mem_write(symbol('request'), struct.pack('<IIiiI', fixture, len(fixture_blob), 255, 0, 5))
                u.mem_write(symbol('request_tick'), struct.pack('<I', synthetic_tick | 1))
                u.mem_write(symbol('request_mode'), struct.pack('<I', 1))
                u.mem_write(counter, struct.pack('<I', 0xffffffe0))
                before = target_calls[0]
                assert invoke(1) == 0, ('APP bench result', app, base, backend)
                sample = struct.unpack('<IIIiIII7I', u.mem_read(symbol('samples'), 56))
                assert sample[:7] == (1, 0, 7, 0, fixture, fixture, 0) and sample[7:] == (17,) * 7, ('APP bench sample', sample)
                assert target_calls[0] - before == (49 if app['route'] == 'shared' else 0)
                forwarded += target_calls[0] - before
                bench_search_calls += 49
                bench_runs += 1
                u.mem_write(symbol('request_mode'), bytes(4))
            before = target_calls[0]
            assert invoke(1) == 0
            runs += 1
            checks += 576
            forwarded += target_calls[0] - before
            # The real packed timing core must reject both an invalid oracle
            # before any search, and a stopped supplied timer in its first round.
            u.mem_write(symbol('request_mode'), struct.pack('<I', 1))
            u.mem_write(symbol('request') + 12, struct.pack('<i', 1))
            before = target_calls[0]
            assert invoke(1) == 2 and target_calls[0] == before
            negative += 1
            u.mem_write(symbol('request') + 12, bytes(4))
            u.mem_write(symbol('request_tick'), struct.pack('<I', wrong | 1))
            assert invoke(1) == 4
            stopped = struct.unpack('<IIIiIII7I', u.mem_read(symbol('samples'), 56))
            assert stopped[1:3] == (4, 0) and stopped[7:] == (0,) * 7
            negative += 1
            u.mem_write(symbol('request_mode'), bytes(4))
            if app['route'] == 'shared':
                u.mem_write(table + 18 * 4, struct.pack('<I', wrong | 1))
                assert invoke(1) == 10
                negative += 1
            assert bytes(u.mem_read(fixture, len(fixture_blob))) == fixture_blob
            assert bytes(u.mem_read(base, image_bytes)) == blob[:image_bytes], 'APP image changed'
            if app['route'] == 'standalone':
                assert not queries
        row = {k: app[k] for k in ['arch', 'route', 'variant', 'strchr_bytes', 'strchr_sha256', 'APP', 'ELF']}
        row.update(load_addresses=[0x20002000, 0x20006000, 0x2000a000], successful_initializations=inits,
                   successful_runs=runs, checks=checks, runtime18_calls=forwarded, negative_checks=negative,
                   cached_reentry=True, SRAM_and_external_Flash=True, synthetic_bench_runs=bench_runs,
                   synthetic_bench_search_calls=bench_search_calls, synthetic_interval_ticks=17)
        results.append(row)
        print(arch, app['route'], app['variant'], checks, 'packed APP strchr checks PASS', flush=True)
    result = dict(status='PASS_REAL_PACKED_SDK_APPS_STRCHR_HOST_ONLY', physical_IO=0, hardware_winner=None,
                  API_discovery='modeled query/capabilities; actual ARM startup/bind/tails/bodies',
                  production_format_decoders=readers, results=results,
                  total_checks=sum(r['checks'] for r in results), total_runtime18_calls=sum(r['runtime18_calls'] for r in results))
    (out / 'decode-commands.json').write_text(json.dumps(logs, indent=2) + '\n')
    (out / 'RESULTS.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--core-dir', type=Path, required=True)
    p.add_argument('--build-only', action='store_true')
    p.add_argument('--run-existing', action='store_true')
    a = p.parse_args()
    data = json.loads((a.output_dir / 'build.json').read_text()) if a.run_existing else build(a.toolchain_bin, a.output_dir, a.core_dir)
    if not a.build_only:
        execute(data, a.core_dir, a.output_dir)


if __name__ == '__main__':
    main()
