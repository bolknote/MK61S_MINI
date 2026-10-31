#!/usr/bin/env python3
"""Bind bounded strlen APPs to a sealed, file-backed research firmware.

This program only builds host artifacts. It never opens a device or lease.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage

LENGTHS = [0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128,
           255, 256, 511, 512, 1023, 1024, 2047, 2048]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=sha(data))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def at(elf, address, size):
    spans = [(elf.data[offset + address - va:offset + address - va + size], pa + address - va)
             for kind, offset, va, pa, fs, _ms, _flags, _align in elf.segments
             if kind == 1 and va <= address and address + size <= va + fs]
    assert spans and all(item == spans[0] for item in spans), (hex(address), size)
    assert len(spans[0][0]) == size
    return spans[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', choices=['m0', 'm4'], required=True)
    parser.add_argument('--firmware-elf', type=Path, required=True)
    parser.add_argument('--firmware-bin', type=Path, required=True)
    parser.add_argument('--firmware-manifest', type=Path)
    parser.add_argument('--kernels', type=Path, required=True, help='V2 SRAM kernels with actual runtime')
    parser.add_argument('--fixture-kernels', type=Path, required=True, help='Leaf-only V1 SRAM kernels')
    parser.add_argument('--fixture-manifest', type=Path, required=True)
    parser.add_argument('--arm-toolchain-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    assert re.fullmatch(r'/STLN[A-Z0-9-]{1,10}', args.directory)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    flash = 0x10000000 if args.cpu == 'm0' else 0x08000000
    binary = args.firmware_bin.read_bytes()
    elf = ElfImage(args.firmware_elf)
    ke = ElfImage(args.kernels / 'kernels.elf')
    fe = ElfImage(args.fixture_kernels / 'kernels.elf')
    fixture = json.loads(args.fixture_manifest.read_text())
    fixture_proof = fixture['kernels'][args.cpu]
    names = ['baseline', 'libc_strlen', 'byte1', 'byte4', 'word1', 'word2', 'word4']
    if args.cpu == 'm4':
        names += ['dsp1', 'dsp4', 'dsp8', 'dsp32']

    def backed(address, size):
        body, physical = at(elf, address, size)
        assert flash <= physical and physical + size <= flash + len(binary)
        assert body == binary[physical - flash:physical - flash + size]
        return body, physical

    footer_name = 'mk61_picocalc_firmware_footer' if args.cpu == 'm0' else 'mk61_resident_firmware_footer'
    footer_address = elf.symbols[footer_name]
    assert elf.sizes[footer_name] == 40
    footer, _ = backed(footer_address, 40)
    fields = struct.unpack('<8sHH7I', footer)
    expected_profile = 0x50434831 if args.cpu == 'm0' else 0xbe204470
    assert fields[:4] == (b'MK61FWC\0', 1, 40, flash)
    assert fields[4] == len(binary) and fields[5] == fields[6] != 0
    assert fields[7:] == (expected_profile, 1, 0)
    canonical = bytearray(binary)
    canonical[footer_address-flash+20:footer_address-flash+28] = bytes(8)
    assert zlib.crc32(canonical) == fields[5]
    if args.cpu == 'm0':
        assert args.firmware_manifest
        fm = json.loads(args.firmware_manifest.read_text())
        build = int(fm['build_id'], 16)
        assert fm['bin_sha256'] == sha(binary)
        assert int(fm['firmware_integrity']['crc32'], 16) == fields[5]
        evidence = {}
        for symbol in ['_ZN8picocalc11diagnostics13status_reportEPcj',
                       '_ZN8picocalc11diagnostics13capture_faultEPKmS2_mmmmm']:
            start = elf.symbols[symbol] & ~1
            body, _ = backed(start, elf.sizes[symbol])
            candidates = []
            for i in range(0, len(body)-3, 2):
                address = start+i
                if address % 4 or body[i:i+4] != struct.pack('<I', build):
                    continue
                loads = [start+j for j in range(0, len(body)-1, 2)
                         if (word := struct.unpack_from('<H', body, j)[0]) & 0xf800 == 0x4800
                         and ((start+j+4) & ~3) + 4*(word & 255) == address]
                if loads:
                    candidates.append(dict(address=address, loads=loads))
            assert len(candidates) == 1, (symbol, candidates)
            evidence[symbol] = candidates[0]
        build_literal = next(iter(evidence.values()))['address']
        services_name = '_ZN8picocalc10NativeHost6commonE'
        runtime_name = '_ZN8picocalc14native_runtimeE'
    else:
        build = fields[6]
        build_literal = footer_address + 24
        evidence = dict(source='resident_firmware::build_id reads the sealed footer build_id',
                        address=build_literal)
        services_name = '_ZZN15loadable_module12app_servicesEvE3api'
        runtime_name = '_ZN15loadable_module12_GLOBAL__N_1L7runtimeE'
    runtime_address = elf.symbols[runtime_name]
    services_address = elf.symbols[services_name]
    assert elf.sizes[runtime_name] == 104 and elf.sizes[services_name] == 28
    runtime_bytes, _ = backed(runtime_address, 104)
    services_bytes, _ = backed(services_address, 28)
    runtime = list(struct.unpack('<26I', runtime_bytes))
    assert all(entry & 1 for entry in runtime)
    assert struct.unpack_from('<IHH', services_bytes) == (0x31535953, 2, 28)
    assert struct.unpack_from('<I', services_bytes, 24)[0] == runtime_address
    native = elf.symbols['strlen'] & ~1
    assert runtime[20] == native | 1
    native_body, native_physical = backed(native, elf.sizes['strlen'])
    code = elf.symbols['mk61_strlen_flash_code']
    code_body, physical = backed(code, elf.sizes['mk61_strlen_flash_code'])
    assert code == physical and not code % 16
    assert len(code_body) == fixture_proof['blob_bytes'] and sha(code_body) == fixture_proof['blob_sha256']
    strings = elf.symbols['mk61_strlen_flash_strings']
    strings_body, physical = backed(strings, elf.sizes['mk61_strlen_flash_strings'])
    assert strings == physical and not strings % 16 and len(strings_body) == 16512
    for copy in range(8):
        expected = bytes(((i*31+(i>>3)*7) % 255)+1 if i < 2048+copy else
                         0 if i == 2048+copy else 1 for i in range(2064))
        assert strings_body[copy*2064:(copy+1)*2064] == expected
    leaves = []
    for name in names:
        size = fe.sizes[name]
        offset = fixture_proof['functions'][name]['offset']
        body, _ = at(fe, fe.symbols[name] & ~1, size)
        body2, _ = at(ke, ke.symbols[name] & ~1, ke.sizes[name])
        assert size == ke.sizes[name] and body == body2
        if offset is not None:
            assert body == code_body[offset:offset+size] and offset % 16 == 0
        leaves.append(dict(name=name, offset=offset, bytes=size, sha256=sha(body), crc32=zlib.crc32(body)))
    anchor = dict(status='PASS_HOST_ANCHORS_NO_HARDWARE', cpu=args.cpu,
        fixture_manifest=pin(args.fixture_manifest), phase=fixture.get('m4_phase','all') if args.cpu=='m4' else 'all',
        firmware=dict(ELF=pin(args.firmware_elf), BIN=pin(args.firmware_bin),
                      manifest=pin(args.firmware_manifest) if args.firmware_manifest else None),
        build=build, crc32=fields[5], footer_address=footer_address, footer=list(footer),
        build_literal=build_literal, build_literal_evidence=evidence,
        services_address=services_address, runtime_address=runtime_address, runtime=runtime,
        native=dict(entry=native|1, bytes=len(native_body), crc32=zlib.crc32(native_body),
                    sha256=sha(native_body), initializer=native_physical),
        flash_code=dict(address=code, bytes=len(code_body), crc32=zlib.crc32(code_body), sha256=sha(code_body)),
        flash_data=dict(address=strings, bytes=len(strings_body), crc32=zlib.crc32(strings_body),
                        sha256=sha(strings_body), stride=2064, limit=2048), leaves=leaves,
        hardware_access=False, hardware_GO=False)
    write(out / 'anchors.json', anchor)
    header = ''.join(f'#define {name} 0x{value:x}u\n' for name, value in dict(
        TARGET_BUILD=build, TARGET_CRC=fields[5], FOOTER_ADDRESS=footer_address,
        BUILD_LITERAL_ADDRESS=build_literal, RUNTIME_TABLE=runtime_address,
        NATIVE_STRLEN=native, NATIVE_BYTES=len(native_body), NATIVE_CRC=zlib.crc32(native_body),
        FLASH_CODE=code, FLASH_CODE_BYTES=len(code_body), FLASH_CODE_CRC=zlib.crc32(code_body),
        FLASH_STRINGS=strings, FLASH_STRINGS_BYTES=len(strings_body), FLASH_STRINGS_CRC=zlib.crc32(strings_body),
        FLASH_STRIDE=2064).items())
    for name, values, ctype in [('expected_runtime', runtime, 'uint32_t'), ('expected_footer', list(footer), 'uint8_t'),
                                ('leaf_offsets', [leaf['offset'] if leaf['offset'] is not None else 0xffffffff for leaf in leaves], 'uint32_t'),
                                ('leaf_sizes', [leaf['bytes'] for leaf in leaves], 'uint32_t'),
                                ('leaf_crcs', [leaf['crc32'] for leaf in leaves], 'uint32_t')]:
        header += f'static const {ctype} {name}[{len(values)}]={{' + ','.join(f'0x{v:x}u' for v in values) + '};\n'
    (out / 'binding.h').write_text(header)
    inputs = out / 'inputs'
    inputs.mkdir()
    corpus = []
    for length in LENGTHS:
        for align in range(8):
            for source in range(2):
                copy = (length+align) & 7
                start = copy*2064+2048+copy-length
                text = strings_body[start:start+length+1]
                assert start % 8 == align and len(text) == length+1 and text[-1] == 0 and 0 not in text[:-1]
                corpus.append([length, align, source, 16384//(length+16), copy, 0])
    batches = []
    for first in range(0, len(corpus), 7):
        rows = corpus[first:first+7]
        raw = struct.pack('<4I', 0x53544c49, 1, len(rows), first)
        raw += b''.join(struct.pack('<6I', *row) for row in rows) + bytes(24*(7-len(rows)))
        assert len(raw) == 184
        path = inputs / f'{first//7:03}.bin'
        path.write_bytes(raw)
        batches.append(dict(first=first, rows=rows, input=pin(path), crc32=zlib.crc32(raw)))
    write(out / 'corpus.json', dict(lengths=LENGTHS, groups=len(corpus), batches=batches, rounds=7,
        order='(round + row_in_batch + (odd_round ? function_count-1-order : order)) % function_count',
        controls='control-before, baseline-before, all functions, baseline-after, control-after',
        input_bytes=184, matched_string_bytes=True))
    apps = []
    for bank in ['sram', 'flash']:
        for shared in [False, True]:
            key = ('shared' if shared else 'standalone') + '-' + bank
            target = out / key
            target.mkdir()
            for name in ['benchmark.c', 'runtime_binding.c', 'candidates.S']:
                shutil.copyfile(HERE / name, target / name)
            shutil.copyfile(out / 'binding.h', target / 'binding.h')
            wrapper = target / 'wrapper.c'
            wrapper.write_text('#define BENCH_ROOT ' + json.dumps(args.directory) + '\n' +
                ('#define BENCH_CODE_FLASH 1\n' if bank == 'flash' else '') +
                '#include "benchmark.c"\n')
            command = [sys.executable, '-B', str(ROOT / 'tools/build_portable_app.py'),
                '--target', 'picocalc-pico-h' if args.cpu == 'm0' else 'stm32', '--name', 'STLNBEN',
                '--source', str(wrapper), '--source', str(target / 'candidates.S'),
                '--source', str(target / 'runtime_binding.c'),
                '--library', str(args.kernels / 'baseline-only.o'),
                '--library', str(args.kernels / 'libc.o'), '--library', str(args.kernels / 'runtime.o'),
                '--output-dir', str(target / 'app'), '--arm-toolchain-bin', str(args.arm_toolchain_bin),
                '--packer', str(ROOT / 'tools/.mk61-app/mk61_module_pack.py')]
            if shared:
                command.append('--shared-runtime')
            result = subprocess.run(command, text=True, capture_output=True,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            (target / 'build.log').write_text(result.stdout+result.stderr)
            assert result.returncode == 0, result.stdout+result.stderr
            ae = ElfImage(target / 'app/STLNBEN.elf')
            leaf_proof = []
            # SRAM bodies must match the Flash fixture's instructions and constants.
            # Flash apps can garbage-collect local candidates after pointer replacement.
            for leaf in leaves:
                name = leaf['name']
                if name not in ae.symbols:
                    assert bank == 'flash'
                    continue
                body, _ = at(ae, ae.symbols[name] & ~1, ae.sizes[name])
                assert len(body) == leaf['bytes'] and sha(body) == leaf['sha256'], name
                leaf_proof.append(dict(name=name, entry=ae.symbols[name]|1, sha256=sha(body)))
            sdk, _ = at(ae, ae.symbols['strlen'] & ~1, ae.sizes['strlen'])
            functions = [code+leaf['offset']+1 if bank=='flash' and leaf['offset'] is not None else ae.symbols[leaf['name']]|1 for leaf in leaves]
            functions += [ae.symbols['strlen']|1, runtime[20], ae.symbols['runtime_strlen']|1]
            image_start = ae.symbols['__module_image_start']
            app = dict(name=key, shared=shared, leaf_code_bank=bank, directory=args.directory,
                command=command, APP=pin(target / 'app/STLNBEN.APP'), ELF=pin(target / 'app/STLNBEN.elf'),
                BIN=pin(target / 'app/STLNBEN.bin'), image_base=image_start,
                image_bytes=ae.symbols['__module_image_end']-image_start,
                memory_bytes=ae.symbols['__module_memory_end']-image_start,
                functions=functions, function_names=names+['sdk_strlen', 'native_cached', 'runtime_strlen'],
                function_relocatable=[not (bank=='flash' and leaf['offset'] is not None) for leaf in leaves]+[True,False,True],
                function_banks=['flash' if bank=='flash' and leaf['offset'] is not None else 'sram' for leaf in leaves]+[
                    'sram-runtime-veneer' if shared else 'sram',
                    'sram' if 0x20000000 <= native < 0x30000000 else 'flash', 'sram-runtime-veneer'],
                leaf_proof=leaf_proof, sdk_strlen=dict(bytes=len(sdk), sha256=sha(sdk)),
                report_bytes=ae.sizes['report'], buffer_offset=ae.symbols['buffer']-image_start,
                report_offset=ae.symbols['report']-image_start,
                control_offset=(ae.symbols['control']&~1)-image_start,
                runtime_pointer_offset=ae.symbols['bench_strlen_runtime']-image_start)
            assert app['memory_bytes'] < 20*1024 and app['report_bytes'] <= 4096
            write(target / 'app.json', app)
            apps.append(app)
            print(args.cpu, key, 'APP', app['APP']['bytes'], 'RAM', app['memory_bytes'], flush=True)
    write(out / 'experiment.json', dict(status='HOST_BUILT_REVIEW_PENDING', cpu=args.cpu,
        anchors=pin(out / 'anchors.json'), corpus=pin(out / 'corpus.json'), apps=apps,
        sources={name:pin(HERE/name) for name in ['benchmark.c', 'candidates.S', 'runtime_binding.c', 'build-experiment.py']},
        hardware_access=False, hardware_GO=False, directory=args.directory))


if __name__ == '__main__':
    main()
