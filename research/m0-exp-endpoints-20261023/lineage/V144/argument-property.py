"""Execute the actual new argument helper on ARM against exact Python integers."""
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP

source = work/'ARGCHECK.cpp'
source.write_text('#include "'+str(work/'source/code/native_eabi_m0.cpp')+'"\n'+'''
extern "C" unsigned argcheck(const uint32_t *in,m0_eabi::Product *out) {
  PowFastLog q={(uint64_t(in[1])<<32)|in[0],in[2],0,false,0};
  const uint64_t sy=(uint64_t(in[4])<<32)|in[3];
  return pow_small_argument(q,sy,in[5],*out);
}
''')
compiler = '/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-g++'
elf = work/'ARGCHECK.elf'
command = [compiler, '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft', '-Os', '-std=c++17',
           '-fno-lto', '-fno-exceptions', '-fno-rtti', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
           '-ffunction-sections', '-fdata-sections', '-fstack-usage',
           '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1', '-DMK61_USE_COMPACT_LIBM=1',
           '-I'+str(work/'source/code'), '-nostdlib', '-nostartfiles',
           '-Wl,--gc-sections,-e,argcheck,-Ttext=0x08000000', str(source), '-o', str(elf)]
subprocess.run(command, check=True)
undefined = subprocess.check_output([compiler.replace('g++','nm'), '-u', str(elf)], text=True)
assert not undefined.strip(), undefined
machine = Machine(elf, False, stack_bytes=4096, instruction_budget=100000)
rng = random.Random(0x144A260)
cases = []
for shift in range(64, 128):
    for qlo in (0, 1, 1 << 63, (1 << 64)-1):
        for qhi in (0, 1, 65535, (1 << 32)-1):
            for sy in (1 << 52, (1 << 52)+1, (1 << 53)-1):
                cases.append((qlo, qhi, sy, shift))
for _ in range(12000):
    cases.append((rng.getrandbits(64), rng.getrandbits(rng.choice((0, 16, 32))),
                  rng.randrange(1 << 52, 1 << 53), rng.randrange(64, 128)))
digest = hashlib.sha256()
accepted = 0
input_pointer, output_pointer = SP-2048, SP-1984
for qlo, qhi, sy, shift in cases:
    payload = struct.pack('<6I', qlo & 0xFFFFFFFF, qlo >> 32, qhi,
                          sy & 0xFFFFFFFF, sy >> 32, shift)
    machine.uc.mem_write(input_pointer, payload)
    machine.uc.mem_write(output_pointer, b'\xA5'*16)
    ok = machine.call('argcheck', input_pointer, output_pointer, width=32)[0] & 0xFFFFFFFF
    exact = (((qhi << 64) | qlo)*sy) >> shift
    assert ok == int(exact < 1 << 64), (qlo, qhi, sy, shift, ok, exact)
    if ok:
        high, low = struct.unpack('<2Q', machine.uc.mem_read(output_pointer, 16))
        assert high == 0 and low == exact, (qlo, qhi, sy, shift, high, low, exact)
        accepted += 1
    digest.update(payload+struct.pack('<I', ok))
report = dict(status='PASS_ACTUAL_ARM_SCALED_ARGUMENT_EXACT_INTEGER_ORACLE',
              cases=len(cases), accepted=accepted, declined=len(cases)-accepted,
              shifts=list(range(64, 128)), result_sha256=digest.hexdigest(),
              ELF_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
              actual_firmware_helper_source_sha256=hashlib.sha256((work/'source/code/native_eabi_m0_pow_fast.inc').read_bytes()).hexdigest(),
              producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), compiler_command=command,
              scope='The auxiliary ARM wrapper includes the exact firmware C++ source and invokes its actual inline helper. Exact Python bigint products independently verify every shift and decline. Inputs/output occupy reserved test slots belowSP; write low-water is not a callee stack measurement.',
              undefined_imports=[], hardware_accessed=False, production_promoted=False)
(work/'argument-property.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS:', len(cases), 'actual ARM argument products, all64 shifts, exact bigint oracle.', flush=True)
