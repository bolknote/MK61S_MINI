"""Real-ROM decoder within 20 bytes, including all K1/K2 transfers and RET.

This is a budget experiment. Its output shape cannot encode the original
Grundy program. Bootstrap code is reported separately and is never hidden.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/elite'))
from assembler import Assembler, pack_number

BASE = 10000
PREFIX = 10000000
BANK = 24
START = 63

# R0=9, R6=8; R9..RB store high+low/10000, RC=10000, RF=10000000.
# D6 consumes R9, RA, RB; B0 stores to 8,7 / 5,4 / 2,1. FL0 skips
# slots 6 and 3 and exits with R0=1. Slot 6 becomes the input cursor 11.
# The service byte of each output word is supplied by the initial skeleton.
DECODER = bytes.fromhex('56 d6 0e 34 6f 10 b0 14 35 6c 12 6f 10 b0 5d 64 55 56 52')
assert len(DECODER) == 19


def run(runner, name, pairs, ms_values=None):
    a = Assembler()
    m = a.module(0, name)
    if ms_values is not None:
        # Nonempty numeric Ms is ordinary input state, loaded from a DATA bank.
        m.raw(0x1f, 0x56, 25)
    for i, (high, low) in enumerate(pairs):
        # Place the separator between fields before execution. That removes
        # division from the decoder without reducing the eight-digit capacity.
        m.raw(*map(int, str(high)), 0x0a,
              *(int(c) for c in f'{low:04d}')).st(9+i)
    m.set(0, 9).set(6, 8).set(3, 7)
    m.set('C', BASE).set('F', PREFIX)
    m.far(0x53, BANK*112+START)
    if ms_values is not None:
        m.raw(0x1f, 0x56, 25)
    m.op('cx', 'stop')
    banks, info = a.link()
    boot = bytes(banks[0][:info['banks']['0']['used']])
    skeleton = bytearray(63)
    services = (0x49, 0x02, 0x50, 0x5e, 0x51, 0x50, 0x01, 0x50, 0x52)
    for i, byte in enumerate(services):
        skeleton[7*i] = byte
    folder = HERE / 'pair20-probes' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'autoexec.m61').write_text(
        f'reinit\nhin 0000 {boot.hex()}\n'
        f'hin {BANK*112:04d} {skeleton.hex()}\n'
        f'hin {BANK*112+START:04d} {DECODER.hex()}\n'
        + (f'hin {25*112:04d} {b"".join(pack_number(n) for n in ms_values).hex()}\n'
           if ms_values is not None else '')
        + 'run\n')
    p = subprocess.run([str(runner), str(folder)], input='dump\n',
                       capture_output=True, text=True, timeout=20)
    row = dict(name=name, pairs=pairs, decoder_bytes=len(DECODER),
               bootstrap_bytes=len(boot), runner_exit=p.returncode)
    if p.returncode:
        row['stderr'] = p.stderr[-300:]
        return row
    state = json.loads(p.stdout.splitlines()[0])
    values = [1, PREFIX+pairs[2][1], PREFIX+pairs[2][0], 7,
              PREFIX+pairs[1][1], PREFIX+pairs[1][0], 11,
              PREFIX+pairs[0][1], PREFIX+pairs[0][0]]
    expected = bytearray(b''.join(pack_number(n) for n in values))
    # ROM auto-counters store integers right-aligned with order 7, retaining
    # leading zeros. Comparing only the display would miss these exact bytes.
    expected[0:7] = bytes.fromhex('00 01 00 00 00 70 00')
    expected[42:49] = bytes.fromhex('00 11 00 00 00 70 00')
    for i, byte in enumerate(services):
        expected[7*i] = byte
    output = bytes.fromhex(state['output_code'][0])
    row.update(error=state['error'], steps=state['steps'],
               exact=output == expected,
               output=output.hex(' '), expected=expected.hex(' '))
    if ms_values is not None:
        row['ms_restored'] = state['output_code'][1] == b''.join(pack_number(n) for n in ms_values).hex()
    (folder / 'state.json').write_text(json.dumps(state, indent=2)+'\n')
    (folder / 'expanded.raw').write_bytes(output)
    (folder / 'decoder.raw').write_bytes(DECODER)
    return row


def main(runner):
    cases = [
        ('zeros', [(0,0)]*3),
        ('ones', [(1,1)]*3),
        ('maximum', [(9999,9999)]*3),
        ('edges', [(0,9999),(9999,0),(1,9998)]),
        ('alternating', [(1010,9090),(1212,7878),(1111,8888)]),
        ('distinct', [(1,2345),(6789,1234),(5678,9)]),
    ]
    rng = random.Random(20261001)
    for i in range(100):
        cases.append((f'random-{i:03d}', [tuple(rng.randrange(BASE) for _ in range(2)) for _ in range(3)]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda c: run(runner, *c), cases))
    for i, values in enumerate(([1]*9, list(range(-4,5)),
                                [99999999,-99999999,1,-1,17,-17,0,63,112])):
        rows.append(run(runner, f'nonempty-ms-{i}', [(1,2345),(6789,1234),(5678,9)], values))
    (HERE / 'pair20.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows), exact=sum(r.get('exact',False) for r in rows),
                         stopped=sum(r['runner_exit']==0 for r in rows),
                         decoder_hex=DECODER.hex(' '), decoder_bytes=len(DECODER),
                         ms_restored=sum(r.get('ms_restored',False) for r in rows),
                         bootstrap_sizes=sorted(set(r['bootstrap_bytes'] for r in rows)))))
    for r in rows:
        if not r.get('exact'):
            print(json.dumps(r))
            break


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
