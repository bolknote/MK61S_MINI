"""Explore native changes of full code words under a 20-byte decoder budget.

Input words are initial program DATA, imported by K2/K1. Calculator registers
and stack are never injected by the host. These are writer probes, not SFXes.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = (ROOT / "tmp/ms-compression-grandi-2026-10-01/original.raw").read_bytes()
WORDS = [RAW[i:i+7] for i in range(0, len(RAW), 7)]


def word(mantissa, sign, units, tens, exponent_sign=0):
    assert len(mantissa) == 8
    d = [int(c, 16) for c in mantissa[::-1]]
    return bytes([0, *(d[i] | d[i+1] << 4 for i in range(0, 8, 2)),
                  sign | units << 4, tens | exponent_sign << 4])


def run(runner, name, source, slot, body):
    # Import all nine words; execute tested ROM instructions; dump raw output.
    code = bytes.fromhex('1f 56 18 55') + bytes(body) + bytes.fromhex(
        '0d 1f 56 19 55 1f 56 19 55 0d 50')
    folder = HERE / 'block-probes' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'autoexec.m61').write_text(
        f'reinit\nhin 0000 {code.hex()}\nhin {24*112+slot*7:04d} {source.hex()}\nrun\n')
    p = subprocess.run([str(runner), str(folder)], input='dump\n',
                       capture_output=True, text=True, timeout=20)
    row = dict(name=name, source=source.hex(' '), body=bytes(body).hex(' '),
               body_bytes=len(body), runner_exit=p.returncode)
    if p.returncode:
        row['stderr'] = p.stderr[-200:]
    else:
        state = json.loads(p.stdout.splitlines()[0])
        output = bytes.fromhex(state['output_code'][1])[slot*7:slot*7+7]
        row.update(output=output.hex(' '), error=state['error'],
                   steps=state['steps'],
                   matches=[i for i, w in enumerate(WORDS) if output[1:] == w[1:]])
        (folder / 'state.json').write_text(json.dumps(state, indent=2)+'\n')
    return row


def main(runner):
    cases = []
    for lead in ('A', 'E'):
        for units in range(16):
            for tens in (0, 1):
                for opcode in (0xD4, 0xB4):
                    name = f'{lead}-order-{tens:X}{units:X}-op-{opcode:02X}'
                    cases.append((name, word(lead+'2030329', 0, units, tens),
                                  4, [opcode]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda c: run(runner, *c), cases))
    (HERE / 'block-probe.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows), stopped=sum(r['runner_exit']==0 for r in rows),
                         exact=sum(bool(r.get('matches')) for r in rows))))
    for r in rows:
        if r['name'].endswith('D4') and (r['matches'] or r['name'].split('-')[2][1] in '789ABCDEF'):
            print(json.dumps(r))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
