#!/usr/bin/env python3
"""Prepare PicoCalc exp/sin/cos timing against the factory RP2040 v3 ROM."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from check_m0_math_layout import verify
from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import Machine
from tools.firmware.picocalc.build_picocalc import compiler_bin

ROM_SHA256 = 'ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
OFFSETS = {'sin': 0x40, 'cos': 0x3c, 'exp': 0x4c}
TARGET = 'mk61s-picocalc-pico-h'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('production', 'bootrom', 'records', 'output'):
        p.add_argument('--'+arg, required=True, type=Path)
    a = p.parse_args()
    source, bootrom, records, out = (path.resolve() for path in (
        a.production, a.bootrom, a.records, a.output))
    rom = bootrom.read_bytes()
    assert len(rom) == 0x4000 and sha(bootrom) == ROM_SHA256
    assert rom[0x10:0x14] == b'Mu\x01\x03'
    addresses = {op: struct.unpack_from('<I', rom, 0x24c+offset)[0]
                 for op, offset in OFFSETS.items()}
    assert all(0 < address < len(rom) and address&1 for address in addresses.values())
    out.mkdir(parents=True, exist_ok=False)
    image = out/'firmware'
    image.mkdir()
    for name in (TARGET+'.elf',TARGET+'.bin',TARGET+'.uf2','manifest.json'):
        shutil.copy2(source/name, image/name)
    elf, manifest = image/(TARGET+'.elf'), json.loads((image/'manifest.json').read_bytes())
    assert sha(source/elf.name) == sha(elf), 'Production ELF copy differs'
    assert sha(image/(TARGET+'.bin')) == manifest['bin_sha256']
    assert sha(image/(TARGET+'.uf2')) == manifest['uf2_sha256']
    machine = Machine(elf, True, bootrom=bootrom)
    center = ('_ZL10exp_center',) if '_ZL10exp_center' in machine.elf.symbols else ()
    layout = verify(source/elf.name, elf, required=center)
    dump(out/'layout-proof.json', layout)
    reference = Oracle()
    for op, address in addresses.items():
        machine.elf.symbols['rom_'+op] = address
    inputs = out/'inputs'
    inputs.mkdir()
    chunks, profile = [], []
    with gzip.open(records, 'rt') as trusted:
        for line in trusted:
            row = json.loads(line)
            op = row['operation']
            if row['run'] != 'CURRENT' or op not in addresses:
                continue
            data = base64.b64decode(row['input_base64'], validate=True)
            assert hashlib.sha256(data).hexdigest() == row['input_sha256']
            magic, version, index, kind, count, loops, _, _ = struct.unpack_from('<8I', data)
            assert (magic, version, kind) == (0x4D304246, 1, 1) and len(data) == 32+24*count
            symbol = f'_ZN12compact_math{len(op)}{op}Ed'
            owned_address = machine.elf.symbols[symbol]|1
            own_cost, rom_cost = 0, 0
            for x, y, expected in struct.iter_unpack('<3Q', data[32:]):
                want = reference.reference(op, x)
                own, _, cost = machine.call(symbol, x, count=True)
                other, _, ref_cost = machine.call('rom_'+op, x, count=True)
                assert want == expected == own == other, (index, hex(x), hex(want), hex(own), hex(other))
                own_cost += cost
                rom_cost += ref_cost
            path = inputs/f'{index:03d}.bin'
            path.write_bytes(data[:24]+struct.pack('<II',owned_address,addresses[op])+data[32:])
            chunks.append(dict(index=index,stream_index=index,part=0,operation=op,stream=row['stream'],
                               cases=count,kind=kind,loops=loops,input=str(path),input_sha256=sha(path),
                               own_address=owned_address,qfplib_address=addresses[op],
                               reference_kind='RP2040_factory_BootROM_v3',
                               reference_formula=op+'(x)', reference_domain='Finite MPFR-correct samples'))
            profile.append(dict(index=index,operation=op,stream=row['stream'],cases=count,
                                own_mean_instructions=own_cost/count,rom_mean_instructions=rom_cost/count))
    assert len(chunks) == 27 and sum(c['cases'] for c in chunks) == 1255
    directory = '/MK61S-M0-TIMING-ROM'
    fixture = out/'TIMING-fixture.c'
    shutil.copy2(ROOT/'tests/fixtures/m0_math_compare_benchmark.c', fixture)
    wrapper = out/'TIMING.c'
    wrapper.write_text(
        '#define MK61_M0_TIMING_CACHE 1\n'
        '#define MK61_M0_TIMING_BOUNDED_WARMUP 1\n'
        '#define MK61_M0_TIMING_RP2040_ROM_V3 1\n'
        f'#define MK61_MATH_COMPARE_ROOT "{directory}"\n'
        f'#include "{fixture.name}"\n')
    with (out/'app-build.log').open('x') as log:
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/apps/portable/build_portable_app.py'),
                        '--target','picocalc-pico-h','--name','TIMING','--source',str(wrapper),
                        '--shared-runtime','--arm-toolchain-bin',str(compiler_bin(None)),
                        '--output-dir',str(out/'app')],stdout=log,stderr=subprocess.STDOUT,check=True)
    app = out/'app/TIMING.APP'
    dump(out/'benchmark.json', dict(status='HOST_QUALIFIED_NOT_RUN',directory=directory,
        firmware_manifest=manifest,linked_image_bytes=manifest['flash_bytes'],elf_sha256=sha(elf),
        production_layout={k:v for k,v in layout.items() if k!='symbols'},
        layout_proof_sha256=sha(out/'layout-proof.json'),app=str(app),app_sha256=sha(app),chunks=chunks,
        fixture_sha256=sha(fixture),
        app_warmup_us=1000000,warmup_pairs_cap=32768,rounds=12,report_version=5,
        method='Unmodified production image vs factory BootROM v3; MPFR-correct cohort',
        primary_estimator='order_balanced_median',bootrom_sha256=ROM_SHA256,reference_kind='RP2040_factory_BootROM_v3',
        reference_flash_bytes=0,records_sha256=sha(records)))
    dump(out/'host-profile.json',dict(groups=profile,mpfr=reference.version,wrong=0,hardware_timing=False))
    print('PASS:',len(chunks),'groups / 1255 MPFR-correct cases; unmodified production flash')


if __name__ == '__main__':
    main()
