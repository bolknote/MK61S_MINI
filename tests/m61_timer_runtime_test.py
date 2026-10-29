#!/usr/bin/env python3
"""Exercise timer syntax and conditions through the production M61 runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run_case(binary, source, commands=(), start=0):
    with tempfile.TemporaryDirectory(prefix='m61-timer-') as directory:
        Path(directory, 'autoexec.m61').write_text(source)
        result = subprocess.run([binary, directory],
            input='\n'.join(commands)+'\n' if commands else '', text=True,
            capture_output=True, timeout=20,
            env={**os.environ, 'MK61_RUNNER_START_MS': str(start)})
        return result, [json.loads(row) for row in result.stdout.splitlines()]


def main():
    binary = str(Path(sys.argv[1]).resolve())
    source = ('timer 4000\n:loop\nif timer>0 R0= 7\n'
              'if timer==0 R1= 8\nwait 500\nrun :loop\n')
    for start in (0, 0xFFFFFF00):
        result, states = run_case(binary, source,
            ('advance 3999', 'advance 1', 'advance 500'), start)
        assert result.returncode == 0, result.stderr
        assert [s['timer_ms'] for s in states] == [4000, 1, 0, 0], states
        assert states[0]['regs'][0] == 7 and states[0]['regs'][1] == 0
        assert states[-1]['regs'][1] == 8, states[-1]
    for value in (0, 1, 60000):
        result, states = run_case(binary,
            f'timer {value}\n:loop\nwait 500\nrun :loop\n',
            (f'advance {value}',))
        assert result.returncode == 0, result.stderr
        assert states[0]['timer_ms'] == value and states[-1]['timer_ms'] == 0
    for command in ('timer', 'timer -1', 'timer 60001', 'timer 1.5',
                    'timer 50 junk', 'timer pause junk', 'timer resume junk'):
        result, _ = run_case(binary, command+'\nwait 500\n')
        assert result.returncode == 3 and 'Invalid TIMER' in result.stderr, (command, result)
    print('M61 timer runtime: boundaries, prepared conditions, invalid syntax and clock wrap: OK')


if __name__ == '__main__':
    main()
