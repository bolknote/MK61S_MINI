#!/usr/bin/env python3
"""Strict strlen wire decoder; reports preserve raw and negative corrections.

A syntactically valid report alone is not evidence of a physical run. Device
identity, measured clocks, transfer readback and original return are supplied
by the independently reviewed parent transport transaction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import zlib


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def pinned(ref):
    data = Path(ref['path']).read_bytes()
    require(len(data) == ref['bytes'] and hashlib.sha256(data).hexdigest() == ref['sha256'],
            'Changed pinned artifact: ' + ref['path'])
    return data


def context(experiment, app_name, batch):
    root = Path(experiment)
    exp = json.loads(root.read_text())
    anchor = json.loads(pinned(exp['anchors']))
    corpus = json.loads(pinned(exp['corpus']))
    require(0 <= batch < len(corpus['batches']), 'Batch index')
    app = next((a for a in exp['apps'] if a['name'] == app_name), None)
    require(app is not None, 'APP mode')
    for name in ['APP', 'ELF', 'BIN']:
        pinned(app[name])
    for ref in anchor['firmware'].values():
        if ref:
            pinned(ref)
    pinned(anchor['fixture_manifest'])
    row = corpus['batches'][batch]
    input_bytes = pinned(row['input'])
    require(zlib.crc32(input_bytes) == row['crc32'], 'Pinned INPUT CRC')
    return exp, anchor, app, row, input_bytes


def decode(raw, exp, anchor, app, batch, input_bytes):
    functions = len(app['functions'])
    leaves = len(anchor['leaves'])
    rows = len(batch['rows'])
    stride = 24 + 7*4*(functions+4)
    require(len(raw) == 256+7*stride == app['report_bytes'], 'Exact report length')
    words = struct.unpack('<'+'I'*(len(raw)//4), raw)
    h = words[:64]
    require(h[:5] == (0x53544c52, 1, functions, rows, 7), 'Report header')
    require(h[6] in (0, 1) and h[7] in range(6), 'Failure flag/code')
    require(h[6] == (h[7] != 0), 'Failure flag consistency')
    expected = {8:batch['first'], 9:int(app['leaf_code_bank']=='flash'), 10:int(app['shared']),
        12:anchor['build'], 13:anchor['crc32'], 15:125000000 if exp['cpu']=='m0' else 96000000,
        16:anchor['services_address'], 17:anchor['runtime_address'], 18:anchor['native']['entry'],
        20:anchor['native']['entry'] & ~1, 21:anchor['flash_data']['address'], 22:anchor['flash_data']['bytes'],
        24:anchor['flash_code']['address'], 25:anchor['flash_code']['bytes'], 27:zlib.crc32(input_bytes)}
    require(all(h[index] == value for index, value in expected.items()), 'Target/mode/input anchor')
    require(h[11] >> 24 == 0x41 and (h[11] >> 4) & 0xfff == (0xc60 if exp['cpu']=='m0' else 0xc24), 'CPU identity')
    require(h[29] in (0, 1) and h[30] < 8 and h[31] in (0, 1), 'Processor state encoding')
    if exp['cpu']=='m4':
        require(h[31] == 0, 'M4 core ID field')
    base = h[61]-app['report_offset']
    top = 0x20038000 if exp['cpu']=='m0' else 0x20020000
    require(base % 8 == 0 and 0x20000000 <= base < base+app['memory_bytes'] <= top, 'APP allocation bounds')
    require(h[60] == base+app['buffer_offset'] and h[62] == (base+app['control_offset'])|1,
            'Buffer/control allocation')
    delta = base-app['image_base']
    require(list(h[32:32+functions]) == [value+delta if relocate else value
        for value, relocate in zip(app['functions'], app['function_relocatable'])], 'Actual per-function placement')
    crc_start = 32+functions
    leaf_crcs = list(h[crc_start:crc_start+leaves])
    expected_leaves = [leaf['crc32'] for leaf in anchor['leaves']]
    require(not any(h[crc_start+leaves:60]), 'Unused header fields')
    all_checks = functions*rows
    phase = h[7]
    expected_crc = [anchor['native']['crc32'], anchor['flash_data']['crc32'], anchor['flash_code']['crc32']]
    actual_crc = [h[19], h[23], h[26]]
    state_valid = h[28] == h[29] == h[31] == 0 and not (h[30]&1)
    timing = []
    for i in range(7):
        offset = 256+i*stride
        row_raw = raw[offset:offset+stride]
        if i >= rows:
            require(not any(row_raw), 'Unused row must be zero')
            continue
        descriptor = list(struct.unpack_from('<6I', row_raw))
        require(descriptor == batch['rows'][i], 'Exact row descriptor')
        rounds = [list(struct.unpack_from('<'+'I'*(functions+4), row_raw, 24+r*4*(functions+4))) for r in range(7)]
        if phase in (1, 2, 3, 4):
            require(not any(value for rnd in rounds for value in rnd), 'Timing must not start on early failure')
        else:
            maximum = 1000000 if exp['cpu']=='m0' else 96000000
            require(all(0 < value < maximum for rnd in rounds for value in rnd), 'Bounded nonzero raw sample')
        timing.append((descriptor, rounds))
    if phase == 1:
        require(h[5] == 0 and h[14] == 0, 'Preflight phase')
        why = h[63]
        if why in (1,2,3,4):
            require((h[28] != 0 if why==1 else h[28]==0 and h[29]!=0 if why==2 else
                    h[28]==h[29]==0 and h[30]&1 if why==3 else h[28]==h[29]==0 and not(h[30]&1) and h[31]!=0), 'State failure reason')
            require(actual_crc == [0,0,0] and not any(leaf_crcs), 'Pre-anchor failure extent')
        elif why in list(range(10,37))+list(range(40,81)):
            require(state_valid and actual_crc == [0,0,0] and not any(leaf_crcs), 'Anchor-prefix failure extent')
        elif why in (81,82,83):
            bad = why-81
            require(state_valid and actual_crc[:bad] == expected_crc[:bad] and actual_crc[bad] != expected_crc[bad]
                    and not any(leaf_crcs), 'Anchor CRC failure extent')
        elif 256 <= why < 256+leaves:
            bad = why-256
            require(state_valid and actual_crc == expected_crc and leaf_crcs[:bad] == expected_leaves[:bad]
                    and leaf_crcs[bad] != expected_leaves[bad] and not any(leaf_crcs[bad+1:]), 'Leaf CRC failure extent')
        else:
            raise Invalid('Unknown preflight reason')
    else:
        require(state_valid and leaf_crcs == expected_leaves, 'Completed preflight')
        if phase == 5:
            why = h[63]
            require(why in list(range(10,37))+list(range(40,84)), 'Postflight reason')
            if why <= 80:
                require(actual_crc == expected_crc, 'Postflight prefix CRC extent')
            else:
                bad = why-81
                require(actual_crc[:bad] == expected_crc[:bad] and actual_crc[bad] != expected_crc[bad], 'Postflight CRC reason')
        else:
            require(actual_crc == expected_crc, 'Completed firmware/code/data CRC anchors')
        if phase in (2,3):
            require(1 <= h[5] <= all_checks and h[14] == 0, 'Correctness failure count/extent')
            if phase == 2:
                require(h[63] != batch['rows'][(h[5]-1)//functions][0], 'Incorrect-return failure reason')
        else:
            require(h[5] == all_checks, 'Complete correctness count')
            if phase != 4:
                require((200000 if exp['cpu']=='m0' else 19200000) <= h[14] <=
                        (2100000 if exp['cpu']=='m0' else 201600000), 'Warmup duration')
            else:
                require(h[63] == 0 and h[14] <= (2100000 if exp['cpu']=='m0' else 201600000), 'Timer failure extent')
    if phase == 0:
        require(h[63] == 0, 'Success diagnostic field')
    result = dict(status='PASS_WIRE_ONLY' if phase==0 else 'RECOGNIZED_APP_FAILURE', failure_code=phase,
        diagnostic=h[63], hardware_provenance_proved=False, input_crc32=f'{h[27]:08x}',
        cpu=exp['cpu'], firmware_build=f'{h[12]:08x}', firmware_crc32=f'{h[13]:08x}',
        phase=anchor['phase'], app=app['name'], batch_first=batch['first'], allocation=base,
        timer='microseconds' if exp['cpu']=='m0' else 'cycles', correctness_calls=h[5],
        function_names=app['function_names'], function_banks=app['function_banks'],
        actual_entries=list(h[32:32+functions]), raw_sha256=hashlib.sha256(raw).hexdigest(),
        rows=[])
    if phase in (0,5):
        for descriptor, rounds in timing:
            corrected = []
            for rnd in rounds:
                control = (rnd[0]+rnd[-1])/2
                corrected.append([(value-control)/descriptor[3] for value in rnd[2:2+functions]])
            result['rows'].append(dict(input=descriptor, raw=rounds, corrected_per_call=corrected,
                median_per_call=[statistics.median(r[f] for r in corrected) for f in range(functions)],
                baseline_before_after=[[rnd[1],rnd[-2]] for rnd in rounds]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--app', required=True)
    parser.add_argument('--batch', type=int, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    exp, anchor, app, batch, input_bytes = context(args.experiment, args.app, args.batch)
    result = decode(args.report.read_bytes(), exp, anchor, app, batch, input_bytes)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        require(not args.output.exists(), 'Output must be new')
        args.output.write_text(text)
    print(result['status'], app['name'], 'first', batch['first'], 'failure', result['failure_code'])


if __name__ == '__main__':
    main()
