#!/usr/bin/env python3
"""Pure HOST request/report format. Does not import a device or transport module."""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'tests')]
from check_stm32_vectors import ElfImage
from prepare import FLASH_BASE, GUARD, LEAVES, ROWS, ROUNDS, body, pin

REQUEST_MAGIC, REPORT_MAGIC = 0x34494853, 0x34524843
FUNCTIONS, HEADER_WORDS = len(LEAVES) + 2, 96
ROW_BYTES = 12 + FUNCTIONS * ROUNDS * 4
REPORT_BYTES = HEADER_WORDS * 4 + ROWS * ROW_BYTES


def require(condition, message):
    if not condition:
        raise ValueError(message)


def request(template, mode, batch=0, context=None):
    require(mode in (0, 1), 'mode must qualify or measure')
    total = len(template['keys']) * 2
    require(0 <= batch < (total + ROWS - 1) // ROWS, 'batch out of matrix')
    if mode == 0:
        require(batch == 0, 'qualification has no matrix batch')
        first = count = 0
        context = [0] * 6
    else:
        first, count = batch * ROWS, min(ROWS, total - batch * ROWS)
        require(context is not None and len(context) == 6 and any(context), 'freeze qualified context first')
    require(all(isinstance(x, int) and 0 <= x <= 0xffffffff for x in context), 'bad context word')
    token = int(template['run_nonce'], 16)
    raw = struct.pack('<14I', REQUEST_MAGIC, 1, mode, first, count, batch,
                      token & 0xffffffff, token >> 32, *context)
    return raw + struct.pack('<II', zlib.crc32(raw) & 0xffffffff, 0)


def parse_request(raw, template):
    require(len(raw) == 64, 'request must be exactly 64 bytes')
    words = struct.unpack('<16I', raw)
    require(words[0:2] == (REQUEST_MAGIC, 1), 'bad request identity')
    require(words[14] == zlib.crc32(raw[:56]) & 0xffffffff and words[15] == 0, 'bad request CRC/reserved')
    require(words[2] in (0, 1), 'bad request mode')
    expected = request(template, words[2], words[5], list(words[8:14]))
    require(raw == expected, 'request differs from finite matrix/nonce/context')
    return dict(mode=words[2], first=words[3], count=words[4], batch=words[5], context=list(words[8:14]))


def source_case(template, index):
    require(0 <= index < len(template['keys']) * 2, 'case out of range')
    key = template['keys'][index // 2]
    return dict(key, index=index, operand_bank='Flash' if index & 1 else 'SRAM')


def parse_report(raw, input_raw, template, app, decoded, *, allow_fault=False):
    """Verify unmodified raw values and actual loaded/public/runtime addresses.

    `decoded` is the production decoder's complete relocated APP image. The
    report supplies its own load delta, then every target address/code CRC is
    checked against that image or the immutable Flash recipe.
    """
    req = parse_request(input_raw, template)
    require(pin(Path(app['APP']['path'])) == app['APP'] and pin(Path(app['ELF']['path'])) == app['ELF'],
            'packed APP or ELF pin changed')
    require(len(raw) == REPORT_BYTES, 'truncated or oversized report')
    h = list(struct.unpack_from('<%dI' % HEADER_WORDS, raw))
    crc = h[62]
    check = bytearray(raw)
    struct.pack_into('<I', check, 62 * 4, 0)
    require(crc == zlib.crc32(check) & 0xffffffff, 'raw report CRC mismatch')
    require(h[:2] == [REPORT_MAGIC, 1] and h[78] == REPORT_BYTES, 'report format/version drift')
    require((h[4], h[5], h[6], h[10]) == (req['mode'], req['first'], req['count'], req['batch']), 'wrong batch')
    require((h[8], h[9]) == (FUNCTIONS, ROUNDS), 'function/round count changed')
    token = int(template['run_nonce'], 16)
    require(h[11:13] == [token & 0xffffffff, token >> 32], 'wrong run nonce')
    require((h[13], h[14]) == (int(app['shared_runtime']), int(app['code_Flash'])), 'wrong APP route')
    require(h[63] == 0 and h[89] == 0 and h[93:96] == [0, 0, 0], 'reserved report fields changed')
    if h[2]:
        require(allow_fault, 'APP stopped at first fault: %d/%d case=%d target=%d' % (h[2], h[3], h[44], h[45]))
        require(h[2] in range(1, 9) and h[7] <= req['count'], 'invalid first-fault fields')
        return dict(status='HOLD_FIRST_FAULT', header=h, request=req,
                    first_fault=dict(reason=h[2], detail=h[3], case=h[44], function=h[45], sample=h[46:60]),
                    raw_report_crc32=crc, physical_speed_claim=False)
    require(h[3] == 0 and h[7] == req['count'] and h[79] == 0 and not any(h[44:60]), 'incomplete/error-free report mismatch')
    require(h[15] == template['runtime_address'] and h[16] == template['actual_native_address'], 'real runtime18 drift')
    require(h[60] == (template['actual_native_address'] & ~1) and h[61] == template['fixture_base'], 'native/fixture address changed')
    fixture = Path(template['fixture']['path']).read_bytes()
    require(pin(Path(template['fixture']['path'])) == template['fixture'], 'HOST fixture pin changed')
    expected_fixture = zlib.crc32(fixture) & 0xffffffff
    require(h[18] == h[19] == expected_fixture, 'fixture changed during APP')
    resident = Path(template['resident_bin']['path']).read_bytes()
    table_at = template['runtime_address'] - FLASH_BASE
    native_at = (template['actual_native_address'] & ~1) - FLASH_BASE
    native_crc = zlib.crc32(resident[native_at:native_at + template['actual_native_bytes']]) & 0xffffffff
    require(h[17] == h[91] == native_crc, 'actual native code CRC changed')
    require(h[92] == zlib.crc32(resident[table_at:table_at + 104]) & 0xffffffff, 'real runtime table changed')
    require(h[21] == 0 and h[22] == 0 and h[23] & 1 == 0, 'exception/masked/unprivileged context')
    require(h[20] & 0xff00fff0 == 0x4100c240, 'not the qualified Cortex-M4 part')
    require(h[24:26] == h[26:28], 'DWT/DEMCR configuration was not restored')
    require(h[32:38] == h[38:44], 'clock/cache/FPU context changed')
    if req['mode']:
        require(h[32:38] == req['context'], 'observed context differs from frozen qualification')
    require(8 <= h[28] <= 250 and 0 < h[29] < 0x80000000 and h[30] == 96000000, 'timer qualification missing')
    expected_cycles = 96000 * h[28]
    require(abs(h[29] - expected_cycles) <= 192000, 'DWT and wall timer disagree')
    image = ElfImage(Path(app['ELF']['path']))
    origin = app['report']['load_address']
    require('report' in image.symbols and 'storage' in image.symbols, 'missing actual APP layout symbols')
    delta = h[76] - image.symbols['report']
    base = origin + delta
    require(base % 8 == 0 and 0x20000000 <= base and base + len(decoded) <= 0x20020000, 'invalid actual APP load span')
    require(len(decoded) == app['report']['memory_bytes'], 'production decoder memory size changed')
    require(h[77] == image.symbols['storage'] + delta, 'actual SRAM fixture layout changed')
    packed = Path(app['APP']['path']).read_bytes()
    require(h[75] == struct.unpack_from('<I', packed, 52)[0], 'wrong loaded APP image CRC')
    for f, leaf in enumerate(template['leaves']):
        name = 'st_' + leaf['name'] if leaf['name'].endswith('_control') else leaf['symbol']
        actual = template['fixture_base'] + leaf['offset'] if app['code_Flash'] else image.symbols[name] + delta
        require(h[64 + f] == (actual | 1) and h[80 + f] == leaf['crc32'], 'candidate address/code changed')
        if not app['code_Flash']:
            at = (actual & ~1) - base
            require(zlib.crc32(decoded[at:at + leaf['bytes']]) & 0xffffffff == leaf['crc32'],
                    'relocated SRAM candidate body differs')
    public = (image.symbols['strchr'] + delta) & ~1
    require(h[73] == (public | 1) and h[74] == h[16], 'public SDK/runtime route changed')
    public_at = public - base
    public_body = decoded[public_at:public_at + app['public_strchr']['bytes']]
    require(len(public_body) == app['public_strchr']['bytes'] and h[90] == zlib.crc32(public_body) & 0xffffffff,
            'actual relocated public strchr body changed')
    rows = []
    for n in range(ROWS):
        at = HEADER_WORDS * 4 + n * ROW_BYTES
        index, count, address = struct.unpack_from('<3I', raw, at)
        values = struct.unpack_from('<%dI' % (FUNCTIONS * ROUNDS), raw, at + 12)
        if n >= req['count']:
            require(index == count == address == 0 and not any(values), 'unused raw rows are not zero')
            continue
        require(index == req['first'] + n, 'case duplicated/skipped/reordered')
        case = source_case(template, index)
        require(count == case['repeats'], 'repetitions changed after qualification')
        expected_address = (template['fixture_base'] + case['offset'] if index & 1
                            else h[77] + GUARD + case['alignment'])
        require(address == expected_address and address % 4 == case['alignment'], 'operand bank/alignment mismatch')
        require(all(0 < x < 0x80000000 for x in values), 'zero/overflow/missing raw interval')
        rows.append(dict(case=case, address=address, repeats=count,
                         raw=[list(values[f * ROUNDS:(f + 1) * ROUNDS]) for f in range(FUNCTIONS)]))
    return dict(status='PASS_RAW_GROUPS', request=req, header=h, rows=rows,
                APP_load_address=base, raw_report_crc32=crc,
                metric='whole checked indirect-call loop; no empty subtraction', physical_speed_claim=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--mode', choices=['qualify', 'measure'], required=True)
    p.add_argument('--batch', type=int, default=0)
    p.add_argument('--context', help='six comma-separated uint32 words from accepted qualification')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    template = json.loads(a.template.read_text())
    ctx = None if a.context is None else [int(x, 0) for x in a.context.split(',')]
    raw = request(template, int(a.mode == 'measure'), a.batch, ctx)
    with a.output.open('xb') as f:
        f.write(raw)
    print(json.dumps(dict(request=pin(a.output), fields=parse_request(raw, template), physical_IO=0)))


if __name__ == '__main__':
    main()
