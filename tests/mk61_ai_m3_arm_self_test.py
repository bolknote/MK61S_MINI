"""Execute relocated M3 soft-float code in the resident loader; no physical I/O."""
from pathlib import Path
import hashlib
import json
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/picocalc-stm32-runtime-20261107/tests'))
from arm_execution import Target

OUT = ROOT/'.build/mk61ai/m3-linear/module'
t = Target(ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime/arm-harness/harness.elf')
package = (OUT/'M3LINE.S3M').read_bytes()
module = t.load(package)
rng = random.Random(0x4d334149)
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]


def job(raw, steps=0, result=12, replay=False):
    for at in range(0, len(raw), 252):
        t.request(5, struct.pack('<I', at)+raw[at:at+252])
    identifier = struct.unpack('<I', t.request(6, struct.pack('<III', module, len(raw), 1000)))[0]
    if replay:
        assert t.send(t.last_frame) == t.last_reply
    for g in range(steps):
        t.call('harness_tick')
        status = struct.unpack('<7I', t.request(7, struct.pack('<I', identifier)))
        assert status[1:4] == (4 if g+1 == steps else 3, 0, g+1), status
    return t.request(8, struct.pack('<III', identifier, 0, result))


def oracle(xs, weights, halves):
    value = 0.0
    for g in range(len(xs)//32):
        lookup = []
        total = 0.0
        for q in range(8):
            table = [0.0]*16
            for lane in range(4):
                for mask in range(1 << lane):
                    table[mask+(1 << lane)] = f32(table[mask]+xs[g*32+q*4+lane])
            lookup.append(table)
            total = f32(total+table[15])
        weighted = 0.0
        for bit in range(4):
            plane = 0.0
            for q in range(8):
                mask = sum(((weights[g*32+q*4+lane] >> bit) & 1) << lane for lane in range(4))
                plane = f32(plane+lookup[q][mask])
            weighted = f32(weighted+f32(plane*(1 << bit)))
        scale = struct.unpack('<e', struct.pack('<H', halves[g]))[0]
        value = f32(value+f32(f32(weighted-f32(8.0*total))*scale))
    return struct.pack('<f', value)


checked = 0
for columns in (32, 128, 384, 512):
    rows = min(2, (512-16)//(columns//2+columns//16))
    for test in range(8):
        xs = [f32(rng.randint(-32768, 32768)/4096) for _ in range(columns)]
        if test == 0:
            xs = [-0.0]*columns
        expected_ack = lambda n: struct.pack('<III', 0x314c4941, columns, n)
        assert job(struct.pack('<IIII', 0x314c4941, 1, columns, 0)) == expected_ack(0)
        raw = struct.pack('<'+'f'*columns, *xs)
        for at in range(0, len(raw), 512):
            assert job(raw[at:at+512]) == expected_ack(min(at+512, len(raw)))
        data = bytearray(struct.pack('<IIII', 0x314c4941, 2, columns, rows))
        expected = bytearray()
        for r in range(rows):
            weights = [rng.randrange(16) for _ in range(columns)]
            halves = [rng.choice([0, 0x8000, 1, 0x83ff, 0x0400, 0xbc00, 0x3c00, 0x7bff])
                      for _ in range(columns//32)]
            for g in range(columns//32):
                for bit in range(4):
                    for i in range(4):
                        data.append(sum(((weights[g*32+i*8+j] >> bit) & 1) << j for j in range(8)))
            data.extend(struct.pack('<'+'H'*len(halves), *halves))
            expected.extend(oracle(xs, weights, halves))
        actual = job(data, columns//32, rows*4, replay=(test == 0))
        assert actual == expected, (columns, test, actual.hex(), expected.hex())
        checked += rows
t.request(10)
assert t.call('harness_empty') == 1
report = dict(status='M3_LINEAR_ARM_PASS', physical_io=False, physical_timing=False,
              independent_fp32_rows=checked, relocated_module_base=hex(t.module_range[0]),
              native_instructions=t.module_instructions, one_group_per_step=True,
              duplicate_start_idempotent=True, unload_empty=True,
              package_sha256=hashlib.sha256(package).hexdigest())
(OUT/'arm-verification.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
