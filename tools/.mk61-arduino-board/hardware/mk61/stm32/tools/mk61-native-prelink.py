#!/usr/bin/env python3
"""Apply the shared native per-unit policy to Arduino's real sketch objects."""
import json
from pathlib import Path
import subprocess
import sys


def apply(build, sketch, command):
    policy = json.loads((Path(__file__).parent / 'native_compile_policy.json').read_text())
    if policy['schema'] != 1 or '-DMK61_NATIVE_RUNTIME=1' not in command:
        raise ValueError('native Arduino compiler policy/flags mismatch')
    cpp = command[0]
    cc = str(Path(cpp).with_name(Path(cpp).name.replace('g++', 'gcc')))
    cxx_only = {'-std=gnu++17', '-fno-rtti', '-fno-exceptions',
                '-fno-use-cxa-atexit', '-fno-threadsafe-statics'}
    replacements = {}
    objects_exist = any((build / 'sketch').rglob('*.o'))
    for unit in policy['units']:
        if unit.get('mcu') == 'f411' and '-DSTM32F411xE' not in command:
            continue
        name = unit['source']
        source = build / 'sketch' / name
        if not source.is_file():
            source = sketch / name
        objects = list((build / 'sketch').rglob(name + '.o'))
        if len(objects) != 1:
            if not objects_exist:  # Arduino's --only-compilation-database.
                continue
            raise ValueError(f'expected one native object for {name}, found {len(objects)}')
        flags = command[1:]
        compiler = cpp
        if name.endswith('.c'):
            compiler = cc
            flags = [f for f in flags if f not in cxx_only] + ['-std=gnu17']
        actual = [compiler, *flags, *unit['flags'],
                  *('-D' + d for d in unit['defines']), '-I', str(source.parent),
                  str(source), '-o', str(objects[0])]
        subprocess.run(actual, check=True)
        replacements[name] = actual
        print('Native Arduino policy: ' + name, flush=True)
    database = build / 'compile_commands.json'
    if database.is_file():
        entries = json.loads(database.read_text())
        for entry in entries:
            actual = replacements.get(Path(entry['file']).name)
            if actual:
                entry.pop('command', None)
                entry['arguments'] = actual
                entry['file'] = actual[-3]
        database.write_text(json.dumps(entries, indent=2) + '\n')


if __name__ == '__main__':
    try:
        if len(sys.argv) < 5:
            raise ValueError('expected BUILD SKETCH CXX FLAGS...')
        apply(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'MK61s native Arduino prelink: {error}')
