#!/usr/bin/env python3
"""Prepare an M4 APP/Flash-fixture template. Never discover or access devices.

The fixture is an overlay recipe, not a firmware or an authority to program
Flash. A future fresh full snapshot must prove that its destination is erased.
The sealed resident prefix, including its runtime table, stays byte-exact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage

FLASH_BASE, FLASH_BYTES = 0x08000000, 512 * 1024
GUARD, ROUNDS, ROWS = 64, 7, 10
RUNTIME_SYMBOL = '_ZN15loadable_module12_GLOBAL__N_1L7runtimeE'
LEAVES = (
    ('native_control', 'native_strchr'), ('sdk_control', 'sdk_strchr'),
    ('newlib_control', 'strchr'), ('byte1', 'byte1_strchr'),
    ('byte4', 'byte4_strchr'), ('word1', 'word1_strchr'),
    ('word2', 'word2_strchr'), ('dsp1', 'dsp1_strchr'),
    ('dsp2', 'dsp2_strchr'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=sha(data))


def sealed_info(data):
    matches = []
    for at in range(max(0, len(data) - 39)):
        if data[at:at + 8] != b'MK61FWC\0':
            continue
        fields = struct.unpack_from('<8sHH7I', data, at)
        magic, version, size, address, length, crc, build, profile, flags, reserved = fields
        if (version, size, address, length, crc, flags, reserved) != (
                1, 40, FLASH_BASE, len(data), build, 1, 0):
            continue
        raw = bytearray(data)
        raw[at + 20:at + 28] = bytes(8)
        if zlib.crc32(raw) & 0xffffffff == crc:
            matches.append(dict(footer=at, bytes=length, build=build, profile=profile,
                                sha256=sha(data), footer_hex=data[at:at + 40].hex()))
    if len(matches) != 1:
        raise ValueError('one valid sealed resident prefix required')
    return matches[0]


def body(image, name):
    address, size = image.symbols[name] & ~1, image.sizes[name]
    for kind, offset, va, pa, n, memory, flags, alignment in image.segments:
        if kind == 1 and va <= address and address + size <= va + n:
            data = image.data[offset + address - va:offset + address - va + size]
            return address, data
    raise ValueError('symbol has no complete file-backed body: ' + name)


def verify_elf_prefix(image, resident):
    checked = 0
    for kind, offset, va, pa, n, memory, flags, alignment in image.segments:
        if kind != 1 or not n or not FLASH_BASE <= pa < FLASH_BASE + FLASH_BYTES:
            continue
        start = pa - FLASH_BASE
        if start + n > len(resident) or resident[start:start + n] != image.data[offset:offset + n]:
            raise ValueError('ELF/BIN physical segment mismatch')
        checked += 1
    if not checked:
        raise ValueError('resident ELF has no physical Flash segments')


def aligned(value, alignment=16):
    return (value + alignment - 1) & -alignment


def repeats(case):
    # First-hit cases use the actual decisive offset, including NUL. The
    # repetition table is deterministic; no failed measurement is retried.
    work = case['expected_offset'] if case['expected_offset'] >= 0 else case['length']
    return max(1, min(4096, 16384 // (work + 16)))


def case_pairs(plan):
    cases = plan['cases']
    if plan['case_count'] != 1152 or len(cases) != 1152 or plan['rounds'] != ROUNDS:
        raise ValueError('the immutable 1152-case, seven-round matrix is required')
    result = []
    for index in range(0, len(cases), 2):
        ram, flash = cases[index:index + 2]
        if (ram['index'], flash['index'], ram['operand_bank'], flash['operand_bank']) != (
                index, index + 1, 'SRAM', 'Flash'):
            raise ValueError('case bank/index order changed')
        for key in ('length', 'alignment', 'text_hex', 'text_bytes', 'character', 'expected_offset'):
            if ram[key] != flash[key]:
                raise ValueError('SRAM/Flash pair differs: ' + key)
        text = bytes.fromhex(ram['text_hex'])
        char = ram['character'] & 255
        expected = text.find(bytes([char]))
        if (len(text) != ram['text_bytes'] or not text or text[-1] != 0 or
                0 in text[:-1] or len(text) != ram['length'] + 1 or
                expected != ram['expected_offset'] or ram['alignment'] not in range(4) or
                not -32768 <= ram['character'] <= 32767 or len(text) > 513):
            raise ValueError('invalid independently checked case')
        result.append(ram)
    return result


def overlay_snapshot(original, resident, fixture_base, fixture):
    """Pure HOST transformation; the caller supplies a separately accepted snapshot.

    No default snapshot, partial dump, non-erased destination, or replay of an
    earlier overlay is accepted. This function never writes or programs a device.
    """
    sealed_info(resident)
    if len(original) != FLASH_BYTES or original[:len(resident)] != resident:
        raise ValueError('fresh full snapshot must contain the exact resident prefix')
    start = fixture_base - FLASH_BASE
    if (fixture_base % 16 or start < aligned(len(resident) + GUARD, 4096) or
            not fixture or start + len(fixture) > len(original)):
        raise ValueError('fixture range overlaps resident or exceeds physical Flash')
    if original[start:start + len(fixture)] != b'\xff' * len(fixture):
        raise ValueError('fixture destination is not erased; preserve unknown contents')
    result = original[:start] + fixture + original[start + len(fixture):]
    if (result[:start] != original[:start] or
            result[start + len(fixture):] != original[start + len(fixture):]):
        raise ValueError('overlay changed unrelated Flash')
    return result


def c_values(data):
    return ','.join('0x%02xu' % b for b in data)


def prepare(resident_path, elf_path, plan_path, core_build_path, output, namespace, nonce):
    if not re.fullmatch(r'/SCHR4-[A-Z0-9]{2,8}', namespace):
        raise ValueError('use a distinct owned /SCHR4- namespace')
    if not re.fullmatch(r'[0-9a-fA-F]{16}', nonce) or int(nonce, 16) == 0:
        raise ValueError('explicit nonzero 64-bit HOST-template nonce required')
    resident = resident_path.read_bytes()
    info = sealed_info(resident)
    image = ElfImage(elf_path)
    verify_elf_prefix(image, resident)
    table_addr, table = body(image, RUNTIME_SYMBOL)
    actual_addr, actual_native = body(image, 'strchr')
    if len(table) != 26 * 4:
        raise ValueError('current 26-slot runtime required')
    slots = struct.unpack('<26I', table)
    if slots[18] != (actual_addr | 1):
        raise ValueError('real slot18 does not point at actual strchr')
    core = json.loads(core_build_path.read_text())
    product = next(x for x in core['products'] if x['arch'] == 'm4' and x['placement'] == 'flash')
    elf_ref = product['elf']
    reference = Path(elf_ref['path'])
    if pin(reference) != elf_ref:
        raise ValueError('qualified core ELF pin changed')
    qualified = ElfImage(reference)
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    cases = case_pairs(plan)
    fixture_base = FLASH_BASE + aligned(len(resident) + GUARD, 4096)
    fixture = bytearray(b'\xff' * 256)
    leaves, controls = [], []
    for label, symbol in LEAVES:
        original_addr, code = body(qualified, symbol)
        expected = product['bodies'][symbol]
        if len(code) != expected['bytes'] or sha(code) != expected['sha256']:
            raise ValueError('qualified leaf body drift: ' + symbol)
        if original_addr % 4:
            raise ValueError('new literal alignment needs a separate qualification')
        offset = aligned(len(fixture))
        fixture.extend(b'\xff' * (offset - len(fixture)))
        fixture.extend(code)
        leaves.append(dict(name=label, symbol=symbol, offset=offset, bytes=len(code),
                           sha256=sha(code), crc32=zlib.crc32(code) & 0xffffffff,
                           qualified_address=original_addr, template_address=fixture_base + offset,
                           code_alignment=16))
        if label.endswith('_control'):
            controls.append((label, code))
    if actual_native != body(qualified, 'native_strchr')[1]:
        raise ValueError('installed native differs from qualified control; requalify first')
    cache, keys = {}, []
    for case in cases:
        key = (case['text_hex'], case['alignment'])
        text = bytes.fromhex(case['text_hex'])
        if key not in cache:
            start = aligned(len(fixture))
            fixture.extend(b'\xff' * (start - len(fixture)))
            fixture.extend(b'\xa5' * (GUARD + case['alignment']))
            text_at = len(fixture)
            fixture.extend(text)
            fixture.extend(b'\xa5' * GUARD)
            cache[key] = text_at
        keys.append(dict(index=case['index'] // 2, offset=cache[key], length=case['length'],
                         character=case['character'], expected=case['expected_offset'],
                         alignment=case['alignment'], repeats=repeats(case)))
    fixture.extend(b'\xff' * (aligned(len(fixture)) - len(fixture)))
    struct.pack_into('<4s7I', fixture, 0, b'SCF4', 1, len(fixture), fixture_base,
                     len(plan['cases']), len(LEAVES), GUARD, zlib.crc32(actual_native) & 0xffffffff)
    fixture[64:96] = bytes.fromhex(sha(plan_bytes))
    fixture[96:128] = bytes.fromhex(sha(resident))
    if fixture_base + len(fixture) > FLASH_BASE + FLASH_BYTES:
        raise ValueError('guarded matrix cannot fit outside sealed resident')
    # Prove the overlay algorithm on a synthetic erased tail, never private data.
    synthetic = resident + b'\xff' * (FLASH_BYTES - len(resident))
    changed = overlay_snapshot(synthetic, resident, fixture_base, bytes(fixture))
    assert changed[:len(resident)] == resident
    output.mkdir(parents=True, exist_ok=False)
    (output / 'fixture.bin').write_bytes(fixture)
    (output / 'native_compile_source_note.txt').write_text(
        'Raw control bodies come from the qualified immutable core ELF.\n'
        'The actual resident prefix/runtime remain unchanged by the overlay recipe.\n'
        'No physical image, clock, timer or lease is accepted by this HOST template.\n')
    assembly = ['.syntax unified', '.thumb', '.text']
    for label, code in controls:
        name = 'st_' + label
        assembly += ['.balign 16', '.global ' + name, '.type ' + name + ',%function',
                     '.thumb_func', name + ':', '.byte ' + ','.join(str(b) for b in code),
                     '.size ' + name + ',.-' + name]
    assembly.append('.section .note.GNU-stack,"",%progbits')
    (output / 'controls.S').write_text('\n'.join(assembly) + '\n')
    nonce_value = int(nonce, 16)
    definitions = dict(ST_FLASH_BASE=FLASH_BASE, ST_FLASH_BYTES=FLASH_BYTES,
        ST_FIXTURE_BASE=fixture_base, ST_FIXTURE_BYTES=len(fixture),
        ST_FIXTURE_CRC=zlib.crc32(fixture) & 0xffffffff, ST_FOOTER=FLASH_BASE + info['footer'],
        ST_RUNTIME=table_addr, ST_NATIVE=actual_addr, ST_NATIVE_BYTES=len(actual_native),
        ST_NATIVE_CRC=zlib.crc32(actual_native) & 0xffffffff, ST_BUILD=info['build'],
        ST_GUARD=GUARD, ST_ROWS=ROWS, ST_ROUNDS=ROUNDS, ST_LEAVES=len(LEAVES),
        ST_FUNCTIONS=len(LEAVES) + 2, ST_CASES=len(plan['cases']), ST_KEYS=len(keys),
        ST_TOKEN_A=nonce_value & 0xffffffff, ST_TOKEN_B=nonce_value >> 32)
    definitions['ST_NOMINAL_HZ'] = 96000000  # HOST template; physical clock remains UNBOUND.
    header = ['/* HOST template. Rebind after actual release; not a hardware Go. */',
              '#ifndef ST_M4_BINDING_H', '#define ST_M4_BINDING_H']
    header += ['#define %s 0x%xu' % (key, value) for key, value in definitions.items()]
    header += ['#define ST_NAMESPACE ' + json.dumps(namespace),
               'static const uint32_t st_expected_runtime[26]={' + ','.join(hex(x) + 'u' for x in slots) + '};',
               'static const uint8_t st_expected_footer[40]={' + c_values(bytes.fromhex(info['footer_hex'])) + '};',
               'static const uint32_t st_leaf_offsets[ST_LEAVES]={' + ','.join(hex(x['offset']) + 'u' for x in leaves) + '};',
               'static const uint32_t st_leaf_sizes[ST_LEAVES]={' + ','.join(str(x['bytes']) + 'u' for x in leaves) + '};',
               'static const uint32_t st_leaf_crcs[ST_LEAVES]={' + ','.join(hex(x['crc32']) + 'u' for x in leaves) + '};',
               'typedef struct { uint32_t offset; uint16_t length; int16_t character,expected; uint8_t alignment,reserved; } st_key;',
               'static const st_key st_keys[ST_KEYS]={']
    header += ['{%du,%du,%d,%d,%du,0},' % (x['offset'], x['length'], x['character'], x['expected'], x['alignment']) for x in keys]
    header += ['};', '#endif']
    (output / 'binding.h').write_text('\n'.join(header) + '\n')
    recipe = dict(status='HOST_TEMPLATE_NOT_A_HARDWARE_GRANT', physical_IO=0,
        resident_bin=pin(resident_path), resident_elf=pin(elf_path), resident_info=info,
        qualified_core_build=pin(core_build_path), qualified_core_elf=elf_ref, plan=pin(plan_path),
        fixture=pin(output / 'fixture.bin'), fixture_base=fixture_base, fixture_bytes=len(fixture),
        leaves=leaves, keys=keys, runtime_address=table_addr, runtime_count=26, strchr_slot=18,
        actual_native_address=actual_addr | 1, actual_native_bytes=len(actual_native),
        actual_native_sha256=sha(actual_native), native_address_mod16=actual_addr % 16,
        code_alignment_note='Template candidates align16; record addresses and validate final production padding/budgets separately.',
        root_namespace=namespace, run_nonce=nonce.lower(), rows_per_APP_run=ROWS,
        timed_APP_runs_per_mode=(len(plan['cases']) + ROWS - 1) // ROWS,
        APP_modes=['standalone-sram', 'shared-sram', 'standalone-flash', 'shared-flash'],
        requirements_before_any_device_action=[
            'Actual predecessors independently CLOSED; fresh exact coordinator Go and consumed lease.',
            'Fresh accepted full 512KiB snapshot and ELF/BIN source/profile/identity binding.',
            'Overlay target is erased; do not overwrite any unknown non-FF byte.',
            'Qualified original-state/typed/cache/RTC snapshot and exact return supplier/argv.',
            'Accepted finite programming and full readback before executing any fixture code.',
            'Actual clock/power/IRQ/cache and DWT qualification; freeze repetition table before timing.',
            'First fault preserves raw data and stops; no replay or automatic reset/reprogram.',
            'Full original firmware/data/clock return and independent CLOSED.'],
        unbound=['physical full snapshot','actual clock/power/timer','carrier programming supplier',
                 'RTC/state return supplier','exact argv','lease','coordinator hardware Go'],
        hardware_GO=None, hardware_winner=None, synthetic_overlay_preserved_prefix=True)
    recipe['generated'] = [pin(output / x) for x in ['fixture.bin','controls.S','binding.h','native_compile_source_note.txt']]
    (output / 'TEMPLATE.json').write_text(json.dumps(recipe, indent=2) + '\n')
    return recipe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['resident-bin','resident-elf','plan','core-build','output-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--run-nonce', required=True)
    a = p.parse_args()
    r = prepare(a.resident_bin, a.resident_elf, a.plan, a.core_build, a.output_dir,
                a.namespace, a.run_nonce)
    print(json.dumps(dict(template=pin(a.output_dir / 'TEMPLATE.json'),
        fixture_bytes=r['fixture_bytes'], timed_APP_runs_per_mode=r['timed_APP_runs_per_mode'],
        physical_IO=0, hardware_GO=None)))


if __name__ == '__main__':
    main()
