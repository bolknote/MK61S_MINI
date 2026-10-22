"""Rebuild the diagnostic Q64 experiment in a fresh private directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

root = Path(__file__).resolve().parents[2]
public = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-work', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--clang', default='/usr/bin/clang++')
parser.add_argument('--ninja', default='/opt/homebrew/bin/ninja')
args = parser.parse_args()
parent, output = args.parent_work.resolve(), args.output.resolve()
assert output.is_relative_to(root / '.build') and not output.exists()


def fingerprint(tree):
    paths = [tree / 'tools/build_picocalc.py', tree / 'tools/seal_picocalc.py']
    paths += [p for folder in ('code', 'ports/picocalc', 'third_party/fatfs', 'third_party/core_math')
              for p in (tree / folder).rglob('*') if p.is_file() and
              (p.suffix in ('.c', '.cpp', '.h', '.hpp', '.S', '.inc', '.ld', '.pio') or p.name == 'CMakeLists.txt')]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(tree)).encode() + b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()


expected = 'ee374b58d1060232748920b3dec15c3b79ac78b80a79efab733a9ac59d5d06ee'
assert fingerprint(parent / 'source') == expected
output.mkdir(parents=True)
source = output / 'source'
shutil.copytree(parent / 'source', source, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
patch = public / 'experimental-pow.patch'
apply = ['git', 'apply', '--directory=' + str(source.relative_to(root)), str(patch)]
subprocess.run(apply[:2] + ['--check'] + apply[2:], cwd=root, check=True)
subprocess.run(apply, cwd=root, check=True)
unit = next(row for row in json.loads((parent / 'build/compile_commands.json').read_text())
            if row['file'].endswith('/code/native_eabi_m0.cpp'))
command = [arg.replace(str(parent / 'source'), str(source)) for arg in shlex.split(unit['command'])]
obj = output / 'native_eabi_m0.cpp.o'
command[command.index('-o') + 1] = str(obj)
with (output / 'compile.log').open('w') as log:
    subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
kernel = output / 'kernels.o'
flags = [args.clang, '--target=arm-none-eabi', '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
         '-Os', '-std=c++17', '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables',
         '-fno-asynchronous-unwind-tables', '-ffunction-sections', '-fdata-sections']
with (output / 'kernel-compile.log').open('w') as log:
    subprocess.run(flags + ['-c', str(public / 'kernels.cpp'), '-o', str(kernel)],
                   cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
nm = Path(command[0]).with_name('arm-none-eabi-nm')
undefined = subprocess.check_output([str(nm), '-u', str(kernel)], text=True)
allowed = {'_ZN7m0_eabi5clz32Em', '__aeabi_ddiv', 'pow_dyadic128', 'pow_dyadic128_checked'}
assert {line.split()[-1] for line in undefined.splitlines()} <= allowed
lines = subprocess.check_output([args.ninja, '-C', str(parent / 'build'), '-t', 'commands',
                                 'mk61s-picocalc-pico-h.elf'], text=True).splitlines()
line = next(line for line in reversed(lines) if ' -o mk61s-picocalc-pico-h.elf ' in line)
tokens = shlex.split(line)
start = next(i for i, token in enumerate(tokens) if token.endswith('arm-none-eabi-g++'))
end = next((i for i in range(start + 1, len(tokens)) if tokens[i] == '&&'), len(tokens))
link = tokens[start:end]
numeric = next(i for i, arg in enumerate(link) if arg.endswith('/code/native_eabi_m0.cpp.o'))
link[numeric] = str(obj)
link.append(str(kernel))
elf = output / 'diagnostic.elf'
link[link.index('-o') + 1] = str(elf)
for i, arg in enumerate(link):
    if arg.startswith('-Wl,-Map='):
        link[i] = '-Wl,-Map=' + str(output / 'diagnostic.map')
with (output / 'link.log').open('w') as log:
    subprocess.run(link, cwd=parent / 'build', stdout=log, stderr=subprocess.STDOUT, check=True)
assert fingerprint(parent / 'source') == expected
record = dict(status='DIAGNOSTIC_REPRODUCED_NOT_QUALIFIED',
              parent_source_sha256=expected, experimental_source_sha256=fingerprint(source),
              elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
              source_patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
              reference_cpp_sha256=hashlib.sha256((public / 'kernels.cpp').read_bytes()).hexdigest(),
              source_command=command, kernel_command=flags, link_command=link,
              sealed_firmware=False, hardware_accessed=False, root_promoted=False)
(output / 'reproduction.json').write_text(json.dumps(record, indent=2) + '\n')
print('Rebuilt diagnostic ELF:', elf)
print('It retains the parent build stamp and is not an installable firmware image.')
