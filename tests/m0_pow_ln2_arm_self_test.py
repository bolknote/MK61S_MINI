#!/usr/bin/env python3
"""Exhaustively check pow's narrow exponent*ln2 product on ARM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools'))

from build_picocalc import compiler_bin
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-root',type=Path,default=root)
p.add_argument('--toolchain')
p.add_argument('--output-dir',type=Path,default=root/'.build/m0-pow-ln2-arm')
p.add_argument('--json',type=Path,required=True)
a=p.parse_args();a.source_root=a.source_root.resolve()
w=a.output_dir.resolve();w.mkdir(parents=True,exist_ok=True)
helper=a.source_root/'code/native_eabi_m0_pow_ln2.inc'
table=(a.source_root/'code/native_eabi_m0_log70_table.inc').read_text()
low=int(re.search(r'log70_two_low=UINT64_C\((\d+)\)',table)[1])
high=int(re.search(r'log70_two_high=(\d+)U',table)[1])
constant=(high<<64)|low
# All inputs produced by the normal finite log path have |k|<=1023.
# The32-bit part products and middle addition have at most one carry.
assert ((1<<22)-1)*1023<1<<32
assert (((1<<32)-1)>>10)+1<1<<32
source='#include <stdint.h>\nusing U=uint64_t;\nstruct Product {U high,low;};\n'
source+=f'static constexpr U log70_two_low=UINT64_C({low});\nstatic constexpr uint32_t log70_two_high={high}U;\n'
source+='#include "'+str(helper)+'"\n'
source+='extern "C" U test_low(uint32_t n){return pow_log_two70(n).low;}\n'
source+='extern "C" U test_high(uint32_t n){return pow_log_two70(n).high;}\n'
(w/'ln2-test.cpp').write_text(source)
cc=compiler_bin(a.toolchain);elf=w/'ln2-test.elf'
subprocess.run([str(cc/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=c++17','-fno-builtin','-fno-exceptions','-fno-rtti','-nostdlib','-Wl,-Ttext=0x08000000','-Wl,-e,test_low',str(w/'ln2-test.cpp'),'-o',str(elf)],check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(elf)])
m=Machine(elf,True);digest=hashlib.sha256()
for n in range(1024):
    lo=m.call('test_low',n)[0];hi=m.call('test_high',n)[0]
    assert (hi<<64)|lo==constant*n,(n,lo,hi,constant*n)
    digest.update(n.to_bytes(4,'little')+lo.to_bytes(8,'little')+hi.to_bytes(8,'little'))
image=ElfImage(elf)
report=dict(status='PASS',cases=1024,arm_calls=2048,complete_domain=True,
    domain='Unsigned |k|0..1023 from every positive normal binary64 input.',
    result='All80 result bits equal the exact Q70 ln2 integer times |k|.',
    standalone_elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
    helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
    abi='R4-R11,SP and bounded stack writes verified for every call.',
    standalone_wrapper_bytes={n:image.sizes[n] for n in ['test_low','test_high']},
    result_sha256=digest.hexdigest())
a.json.parent.mkdir(parents=True,exist_ok=True)
a.json.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
