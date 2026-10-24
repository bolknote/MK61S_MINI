"""Exact lower enclosure of the unchanged small-h seventh-order polynomial."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
PARENT = ROOT / '.build/m0-atan-directional-ninth-20261024'
source = (W / 'native_eabi_m0_atan_fast.inc').read_text()
assert 'if(!safe && h<(U(1)<<61) && bool(tail<half)!=reverse)' in source
assert 'safe=int32_t(15*repaired_distance)+5*r3_shifted-3*r5>=(normal?34:42);' in source
assert hashlib.sha256((PARENT / 'native_eabi_m0_atan_fast.inc').read_bytes()).hexdigest() == '996dcd240df881b6592b61aeca95fd446c7522b6fff71bc1c6de8eeed9001d23'
S = 1 << 70
cap = F(1, 512)
ez = F(1, 2) + F(13, 512)
e3 = F(1, 2) + F(13, 512) + cap * ez
e5 = (F(1, 2) + cap**2 * e3 + cap**3 * ez + e3 * ez / S +
      ((1 << 17) - 1) * (S * cap**2 + ez) / S +
      ((1 << 24) - 1) * (S * cap**3 + e3) / S)
e7 = (F(1, 2) + cap**2 * e5 + cap**5 * ez + e5 * ez / S +
      7 * (S * cap**2 + ez) / S +
      ((1 << 24) - 1) * (S * cap**5 + e5) / S)
ratio = F(1, 2) + F(35, 1 << 20)
derivative = 33 * (cap + F(33, S))**2
omitted = S * cap**9 / 9
low_normal = e3 / 3 + e5 / 5 + e7 / 7 + F(3, 7) + ratio + F(1, 2) + derivative + omitted
low_wide = low_normal + F(1, 2)
assert 15 * low_normal < 29
assert 15 * low_wide < 37
assert cap * S == 1 << 61
for distance in range(55):
    for r3 in (-1, 0, 1):
        for r5 in range(-4, 10):
            for normal in (False, True):
                assert (15*distance+5*r3-3*r5 >= (29 if normal else 37)) == (
                    15*distance+5*(r3+1)-3*r5 >= (34 if normal else 42))
out = dict(status='PASS_EXACT_SMALL_H_LOWER_ATAN', h_cap=str(cap),
           lower_base_normal=str(low_normal), lower_base_normal_float=float(low_normal),
           lower_base_wide=str(low_wide), lower_base_wide_float=float(low_wide),
           scaled_lower_thresholds=dict(normal=29, wide=37),
           signed_bias='r3/3-r5/5', lower_gate='15*distance+5*r3-3*r5>=threshold',
           equivalent_source_gate='15*distance+5*(r3+1)-3*r5>=34/42',
           direction='only when bool(tail<half)!=(negative!=invert)',
           old_polynomial_not_ninth_corrected=True, runtime_implemented=True,
           source_sha256=hashlib.sha256(source.encode()).hexdigest(),
           inherited_parent_certificate_sha256=hashlib.sha256((PARENT / 'certificate.json').read_bytes()).hexdigest())
(W / 'low-certificate.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
