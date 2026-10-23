"""Bound the new raw Q63 root and propagation through a normalized interval."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import runpy
import struct
import sys

root=Path.cwd()
work=Path(_checkpoint_args.work).resolve()
parent=root/'.build/m0-pow-final-parent-v110-20261023'
generator=root/'tools/generate_m0_sqrt64_table.py'
namespace=runpy.run_path(str(generator))
rows=list(namespace['coefficients']())
packed,old=namespace['packed_coefficients'](rows)
table=parent/'source/code/native_eabi_m0_sqrt64_table.inc'
words=[int(n) for line in table.read_text().splitlines() if line.strip().startswith('.word')
       for n in line.split('.word')[1].split(',')]
assert words==[n for row in packed for n in row]
# The coordinate calculation rounds the truncated Q32 cell coordinate
# directly to Q20, over every full64-bit input, using the same table cells.
coordinate=F(1,1<<21)+F(1,1<<32)
assert coordinate==F(2049,1<<32)
# For even parity N=floor(A/2), changing the seed's real argument by
# less than2^-62. The Q31 root/inverse slope bounds add less than2^-30.
assert F(old['root_seed_error_bound'])+F(1,1<<30)<10
assert F(old['inverse_seed_error_bound'])+F(1,1<<30)<13
residual=2*(1<<32)*10+100
refined=(F(5,8)+F(100,2048)+F(residual*13,1<<42)+F(63*((1<<31)+13),1<<42))
assert refined<1
residual52=refined*((1<<54)+refined)
assert residual52<1<<54
# abs(S)>>22 fits32 bits. A three-product high32 truncates by<3 units;
# shifting19 bits adds<1. The inverse seed contributes <13*S/2^73.
correction=(1+F(1,1<<20)+F(3,1<<19)+13*residual52/F(1<<73)+refined*refined/F(1<<42))
# Even-parity N truncation changes the root by <1/2 Q63 unit.
raw_bound=correction+F(1,2)
assert raw_bound<2<3
# On [A-E,A+E], E<=2^20, the largest normalized root derivative
# is below3/4, including both exponent parities and a lower binade crossing.
assert F(1,2*(1-F(1,1<<43)))<F(9,16)
assert all((3*e+3)//4>=F(3*e,4) for e in range(1000))
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine
elf=work/'raw.elf'
m=Machine(elf,True,stack_bytes=16384,bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
left=[]
for delta in range(8):
    value=m.call('pow_sqrt64_raw',(1<<63)+delta,0)[0]
    assert value>=1<<63
    left.append(dict(input_offset=delta,center=hex(value)))
# For A>=2^63+8, sqrt(A/2^63)*2^63 exceeds2^63+3. The raw
# bound then prevents a lower normalization crossing. The finite remaining
# eight inputs above are checked on the actual machine code.
assert ((1<<63)+8)*(1<<63)>((1<<63)+3)**2
source=(parent/'source/code/native_eabi_m0.S').read_text()
start=source.index(' ldmia r7!,{r0,r1}',source.index('.Lsqrt64_normal:'))
end=source.index(' bmi .Lsqrt64_negative_residual',start)
expected=source[start:end].replace(' mov r7,r0                    // V ~= 2^31/sqrt(m)',
 ' mov r7,r0                    // V ~= 2^31/sqrt(m)\n mov r6,r0                    // Retain inverse seed through the Q52 step.')
assert expected in (work/'root64.S').read_text()
record=dict(status='PASS_FIXED_ROOT_BOUND_CERTIFICATE',existing_coefficient_words=len(words),new_tables=0,
    full64_coordinate_error=str(coordinate),q52_root_error_bound=str(refined),
    q52_residual_absolute_bound=str(residual52),q63_correction_error_bound=str(correction),
    total_point_root_error_bound=str(raw_bound),conservative_raw_radius=3,
    propagated_radius='ceil(3*E/4)+3 for E<=2^20; retain this radius if an upper normalization halves the center.',
    left_normalization_cases=left,unchanged_Q52_Newton_body=True,
    elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    assembly_sha256=hashlib.sha256((work/'root64.S').read_bytes()).hexdigest(),
    generator_sha256=hashlib.sha256(generator.read_bytes()).hexdigest(),
    scope='Extends the existing packed-polynomial certificate to full64-bit arguments, signed residual correction and bounded interval propagation. Does not qualify the complete root-ladder pow prototype, its dispatcher or physical speed.')
(work/'certificate.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: raw error',float(raw_bound),'<2 units; conservative radius3; no new coefficient words.')
