"""Assemble the exact retained-product source and bind it to the used capsule."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0, str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
source = (P/'source/code/native_eabi_m0_product.inc').read_text()
fragments = []
for name in ('product62_pair', 'product62_half1', 'product62_word2', 'product62_half2', 'log_product'):
    matches = re.findall(r'(?ms)^\.macro '+name+r'\b.*?^\.endm\s*$', source)
    assert len(matches) == 1, name
    fragments.append(matches[0])
unit = r'''.syntax unified
.cpu cortex-m0plus
.thumb
.macro log_math_function name
 .section .text.seed,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro end name
 .size \name,.-\name
.endm
'''+ '\n'.join(fragments) + '\nlog_product mk61_m0_log_product46,46,4\n'
(W/'seed-kernel.S').write_text(unit)
command = [str(CC/'arm-none-eabi-gcc'), '-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft',
           '-c', str(W/'seed-kernel.S'), '-o', str(W/'seed-kernel.o')]
subprocess.run(command, check=True)
image = ElfImage(W/'seed-kernel.o')
code = image.bytes_at(image.named_sections['.text.seed'])
proof = json.loads((W/'helper-proof.json').read_text())
assert len(code) == 184 == image.sizes['mk61_m0_log_product46']
assert hashlib.sha256(code).hexdigest() == proof['additional_loaded_seed_code_sha256']
out = dict(status='PASS_SEED_CAPSULE_BYTE_EXACT_FROM_PINNED_ASSEMBLY_SOURCE',
           code_bytes=len(code), code_sha256=hashlib.sha256(code).hexdigest(),
           source_sha256=hashlib.sha256(source.encode()).hexdigest(),
           extracted_macro_sha256=hashlib.sha256('\n'.join(fragments).encode()).hexdigest(),
           command=command, hardware_accessed=False)
(W/'seed-source-proof.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
