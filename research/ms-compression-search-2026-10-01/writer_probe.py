"""Native, keyboard-code producers for exact numeric fields of code words.

Only setup code and initial program-service bytes are injected. No calculator
data registers or stack are injected. Numeric operations and exchanges execute
the real ROM/core. A returned word is inspected as bytes, not as display text.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools/elite"))
from assembler import Assembler

RAW = (ROOT / "tmp/ms-compression-grandi-2026-10-01/original.raw").read_bytes()
WORDS = [RAW[i:i+7] for i in range(0, len(RAW), 7)]


def run(runner, name, body, slot=0, stored=False):
    a = Assembler()
    m = a.module(0, name)
    m.raw(*body)
    if not stored:
        m.st(slot)
    m.op("cx")
    # Preserve destination service tetras, transfer all numerical tetras.
    m.raw(0x1F, 0x56, 24, 0x55, 0x1F, 0x56, 24, 0x55).op("cx", "stop")
    banks, info = a.link()
    used = info["banks"]["0"]["used"]
    folder = HERE / "writer" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "autoexec.m61").write_text(
        f"reinit\nhin 0000 {banks[0][:used].hex()}\nrun\n")
    result = subprocess.run([str(runner), str(folder)], input="dump\n",
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        row = dict(name=name, producer_hex=bytes(body).hex(" "),
                   producer_bytes=len(body)+(not stored), slot=slot,
                   word_hex=None, stopped=False, error=None, matches=[],
                   runner_exit=result.returncode, stderr=result.stderr[-1000:])
        (folder / "failure.json").write_text(json.dumps(row,indent=2)+"\n")
        return row
    state = json.loads(result.stdout.splitlines()[0])
    word = bytes.fromhex(state["output_code"][0])[slot*7:slot*7+7]
    row = dict(name=name, producer_hex=bytes(body).hex(" "),
               producer_bytes=len(body)+(not stored), slot=slot, word_hex=word.hex(" "),
               stopped=not state["running"], error=state["error"], steps=state["steps"],
               matches=[i for i, target in enumerate(WORDS) if word[1:] == target[1:]])
    (folder / "state.json").write_text(json.dumps(state, indent=2)+"\n")
    return row


def digits(n):
    return list(map(int, str(n)))


def main(runner):
    cases = {
        "ordinary": digits(12030330),
        "ordinary-drop-leading": digits(12030330)+[0x48, 0x0C],
        "ordinary-exp-3": digits(12030330)+[0x0C, 3],
        "e-source": [1, 1, 0x3A, 0x35],
        "e-source-recalled": [1, 1, 0x3A, 0x35, 0x4E, 0x6E],
        "super110": [1, 0x0C, 9, 9, 0x0E, 1, 0x0C, 1, 1, 0x12],
    }
    source = [1, 1, 0x3A, 0x35, 0x4E]
    for start in (10000000, 12030330, 12020435, 16145101):
        for steps in range(4):
            body = source + [0x6E, 0x0E] + digits(start) + [0x14, 0x54, 0x0C]
            for j in range(steps):
                body += [0x44, 0xD4, 0x64]
                if j < steps-1:
                    body += [0x6E, 0x64, 0x14, 0x54, 0x0C]
            cases[f"sign-start-{start}-steps-{steps}"] = body
    # Known first-digit splices, with a decimal producer as hidden X2 body.
    for lead in (0, 1, 5, 9):
        cases[f"splice-lead-{lead}"] = digits(12030330)+[0x0E, lead, 0x14, 0x54, 0x0C]
    for start in (12030329, 12020434):
        base = source + [0x6E, 0x0E] + digits(start) + [0x14, 0x54, 0x0C, 0x44, 0xD4]
        final_zero = [0x0E, 0, 0x64, 0x14, 0x54, 0x0C]
        cases[f"zero-sign-{start}"] = base+final_zero
        cases[f"zero-sign-order-{start}"] = base+final_zero+[3]
        cases[f"zero-sign-scaled-{start}"] = base+[0x64, 0x0E, 1, 0x0C, 3, 0x12, 0x48, 0x0E, 0, 0x68, 0x14, 0x54, 0x0C]
    results = [run(runner, name, body) for name, body in cases.items()]
    for index in (1,4):
        start=12030331 if index==1 else 12030329
        body=[1,5,0x3A,0x35,0x49,0x0E]+digits(start)+[0x48,0x69,0x68,0x14,0x54,0x0C,0x40+index,0xD0+index]
        results.append(run(runner,f'A-sign-order7-slot-{index}',body,index,True))
    for exponent in (7, 10, 110):
        for donor in (0,1,5):
            seed = [1,donor,0x3A,0x35,0x49,0x0E]+digits(12030330)
            if exponent != 7:
                seed += [0x0C]+digits(exponent-7)
            # For exponent 110, produce the supernumber before copying it
            # through any normalizing recall. This branch is only a probe.
            if exponent > 99:
                continue
            seed += [0x48,0x69,0x68,0x14,0x54,0x0C]
            for op,tail in [('add-zero',[0x14,0x0D,0x10]),
                            ('sub-zero',[0x14,0x0D,0x11]),
                            ('mul-one',[0x14,0x0D,1,0x12])]:
                results.append(run(runner,f'carry-{donor}-exp-{exponent}-{op}',seed+tail))
    # Normalizing A/F at an indirect-address pointer can carry into its sign
    # nibble. Inspect that pointer directly; recalling it would renormalize it.
    for index in (0, 1, 3, 4, 5, 6):
        target = WORDS[index]
        mantissa = ''.join(f'{b:02x}' for b in target[1:5][::-1])
        lower = mantissa[1:]
        if any(c not in '0123456789' for c in lower):
            continue
        step = -1 if index < 4 else 1
        start = int('1'+lower)-step
        exponent = (target[6]&15)*10+(target[5]>>4)
        source_digit = 5 if mantissa[0] == '0' else 0
        body = [1, source_digit, 0x3A, 0x35, 0x49, 0x0E] + digits(start)
        if exponent != 7:
            body += [0x0C]+digits(exponent-7)
        body += [0x48, 0x69, 0x68, 0x14, 0x54, 0x0C, 0x40+index]
        results.append(run(runner, f"A-F-normalize-word-{index}", body+[0xD0+index], index, True))
        results.append(run(runner, f"A-F-indirect-store-word-{index}", body+[0x0D,0xB0+index], index, True))
        if index < 4:
            op = {0:0x5D,1:0x5B,2:0x58,3:0x5A}[index]
            address=len(body)+2
            results.append(run(runner,f"A-F-loop-word-{index}",body+[op,(address//10)*16+address%10],index,True))
    (HERE / "writer-probe.json").write_text(json.dumps(results, indent=2)+"\n")
    for row in results:
        print(json.dumps(row))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
