#!/usr/bin/env python3
"""PicoCalc services HIL. Writes two uniquely named test sources, never formats.

Uses the visible keyboard routes and the foreground CDC terminal. ENQ reads
status even inside an editor/INPUT, where '?' and '!' are ordinary source.
"""
import argparse
import json
import os
from pathlib import Path
import re
import select
import termios
import time
import tty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--write-test-files', action='store_true', required=True)
    args = parser.parse_args()
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = termios.tcgetattr(fd)
    transcript = []
    cases = []
    stamp = time.strftime('%Y%m%d-%H%M%S')
    sources = {}

    def read_for(seconds):
        data = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([fd], [], [], max(0, end-time.monotonic()))[0]:
                chunk = os.read(fd, 16384)
                if not chunk:
                    raise RuntimeError('Pico disconnected')
                data += chunk
        text = data.decode('utf-8', errors='replace')
        transcript.append(text)
        print(text, end='', flush=True)
        return text

    def query():
        os.write(fd, b'\x05')
        return read_for(.3)

    def step(keys, expected):
        os.write(fd, keys)
        read_for(.2)
        state = ''
        end = time.monotonic() + 8
        while time.monotonic() < end:
            state += query()
            if expected in state:
                return state
        raise RuntimeError(f'Expected {expected}')

    def save(name, source):
        step(source.encode('ascii'), f'SOURCE={len(source)} DIRTY=1')
        step(b'\x82', 'SERVICE=PROMPT')
        step(b'\x08'*7 + name.encode('ascii') + b'\n', f'DIRTY=0 PATH=[/{name}]')
        sources[name] = source
        cases.append(f'Editor saved {name}')

    try:
        tty.setraw(fd)
        read_for(.2)
        status = query()
        if 'MK61S PICOCALC PICO-H' not in status or 'SD=OK' not in status:
            raise RuntimeError('Expected PicoCalc with mounted microSD')
        if 'UI=CALCULATOR' not in status or 'SERVICE=CLOSED' not in status:
            raise RuntimeError('Start this test from the calculator screen')
        step(b'\t' + bytes([0xB5])*6 + bytes([0xB6])*4 + b'\n', 'SERVICE=DEVELOPMENT')
        step(bytes([0xB6])*3 + b'\n', 'SERVICE=LANGUAGE')
        step(b'\n', 'SERVICE=EDITOR')
        basic = ('10 PRINT "PICO BASIC=!",2+3\n'
                 '20 .R0=SQRT(9)+SIN(90)\n'
                 '30 INPUT N\n'
                 '40 .R1=N*2\n'
                 '50 .X=.R1+.R0\n'
                 '60 PSET 10,20\n'
                 '70 PRINT POINT(10,20)\n'
                 '80 END\n')
        save(f'MK61S-HIL-{stamp}.bas', basic)
        os.write(fd, b'\x83')
        output = read_for(2)
        if 'N:' not in output or 'VM_RESULT=' in output:
            raise RuntimeError('BASIC did not wait for numeric INPUT')
        os.write(fd, b'12\n')
        output += read_for(2)
        if 'VM_RESULT=OK' not in output:
            raise RuntimeError('BASIC INPUT/graphics run failed')
        status = query()
        raw = re.search(r'X_RAW=\[([^]]+)\]', status)[1]
        value = float(raw[:10].replace(' ', '').replace(',', '.')) * 10**int(raw[11:].replace(' ', ''))
        if value != 28:
            raise RuntimeError(f'BASIC shared calculator references: X={value}, expected 28')
        cases.append('BASIC compile/run, PRINT, INPUT, math, MK61 registers and graphics')
        step(b'\x1B', 'SERVICE=EDITOR')
        step(b'\x1B', 'SERVICE=LANGUAGE')
        step(b'\x1B', 'SERVICE=DEVELOPMENT')
        step(bytes([0xB6])*2+b'\n', 'SERVICE=LANGUAGE')
        step(b'\n', 'SERVICE=EDITOR')
        focal = ('1.10 SET A=2+3; PRINT "PICO FOCAL=",A,!\n'
                 '1.20 SET .X=SQRT(81); EXIT\n')
        save(f'MK61S-HIL-{stamp}.foc', focal)
        os.write(fd, b'\x83')
        output = read_for(2)
        if 'VM_RESULT=OK' not in output or 'PICO FOCAL=' not in output:
            raise RuntimeError('FOCAL run failed')
        cases.append('FOCAL compile/run, PRINT and shared math/registers')
        step(b'\x1B', 'SERVICE=EDITOR')
        step(b'\x1B', 'SERVICE=LANGUAGE')
        step(b'\x1B', 'SERVICE=DEVELOPMENT')
        step(b'\x1B', 'SERVICE=CLOSED')
        final = step(b'\t', 'UI=CALCULATOR')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(port=args.port, cases=cases, sources=sources,
            final_status=final, transcript=transcript, passed=True), ensure_ascii=False, indent=2)+'\n')
        print('PicoCalc services HIL passed')
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        os.close(fd)


if __name__ == '__main__':
    main()
