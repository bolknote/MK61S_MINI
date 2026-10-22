# Checked cubic pow near one on RP2040

V90 adds a direct binomial path for positive bases within `2^-47` of one,
with `2^-11 <= |y| < 32`. It remains an isolated prototype over frozen V87;
ROOT production math and the physical PicoCalc firmware are unchanged.

The [measurement report](../../doc/measurements/m0-pow-binomial-v90-20261022.json)
pins the source, ELF, ROM, test programs, inputs and results. The
[one-file patch](binomial-pow.patch) applies after the V87 checked-pow patch.

## Result and limits

Four saved difficult inputs now complete in 974–988 ARM instructions instead
of 105,034–108,884. Original Qfplib's composed `exp(mul(y,ln(x)))` takes
1,302–1,328 instructions on those inputs. Every owned result matches directed
MPFR. This Qfplib has no standalone pow entry.

| Difficult stream | Cases | V87 instructions/call | V90 instructions/call | Qfplib instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 19,006.65 | 15,686.77 | 1,501.55 |
| Near one, large exponents | 5 | 1,474.20 | 1,491.60 | 1,573.80 |
| Moderate bases/exponents | 128 | 15,114.83 | 15,125.58 | 1,535.45 |

The regular hard stream improves by about 17.5%. The new dispatcher guard
adds up to 17 instructions to several existing pow stream means; each remains
below its Qfplib reference. No non-pow stream changes its instruction counts.
The complete unchanged matrix has 117 groups, 119 chunks and 23,352 cases:
113 groups use fewer instructions than Qfplib, two tie and two remain slower.
Qfplib differs from MPFR on 63, 5 and 71 inputs in the three difficult streams.
Owned mismatches are zero.

These are actual executed ARM instructions with captured RP2040 ROM code,
using the production ELF for owned functions and the pinned V87 diagnostic
ELF for Qfplib. They are not physical cycles, XIP measurements or a universal
speed guarantee. Two difficult pow streams still have substantial speed gaps.
General pow totality remains unproved; the final undecided interval trap is
retained. The return-value contract is RNE; errno and FP flags are not added.

## Arithmetic and qualification

For `f=x-1`, the new helper evaluates the first three binomial terms around
the exact unit baseline. The linear term is exact in Q160. The quadratic
term uses an exact product of at most 129 bits and one floor. The cubic
coefficient uses Q32 products, with a Lipschitz/floor error bound, followed
by the existing certified integer division by three. Taylor's fourth
derivative bounds the remainder. The combined absolute error is below two
Q160 units; the code reserves four and declines ambiguous rounding cells.
There is no new table or allocation.

The exact-rational certificate covers all accepted exponent/side ranges,
integer widths, shift domains, the sign of the displacement, product/floor
errors and the existing divide-by-three residual correction. A separate ARM
test checks 14,180 cases: 10,393 helper acceptances, one ambiguous decline,
3,786 domain declines and 614 public pow/MPFR calls. Every accepted result's
binary64 cell strictly contains an independently computed rational cubic
Taylor interval, and every accepted result also matches directed MPFR.

All 265,409 calls across the twelve functions pass ARM/MPFR qualification.
All 787 entries of the existing 1,003,177-case corpus that reach the new
public dispatch gate were selected exhaustively and replayed successfully.
The older full-million result belongs to V86; it is not relabeled as a V90
run. V90's unchanged paths are supported by object/link identity evidence.

Cortex-M4 soft/hard O3 output and non-RP2040 ARMv6-M allocated output remain
identical to their established baselines. Four other numerical objects and
their relocation targets are identical to V87. Every prior function in the
changed native object, except the dispatcher, retains its instruction bytes.
All 224 inspected non-pow linked functions keep their addresses and bytes.

Allocated Flash grows by 2,040 bytes over V87. The image extent remains
1,537,008 bytes, main static RAM 198,856, heap 30,520, and scratch reservation
4,096. The scratch object bytes are identical; two linked RAM veneer slots
are permuted and both callers are checked against equivalent targets. The
unchanged rsqrt seed payload moves by 80 bytes. Physical cache effects still
need measurement on the final accepted platform/memory composition.

The preceding Q128 two-term experiments were numerically correct but did
not resolve these hard cases. Their domains and error bounds caused the
correct fallback, so only the Q160 cubic candidate is preserved here as the
proposed optimization.

## Reproduction

Prepared candidate: `.build/m0-pow-binomial160-v90-20261022`.

```
python tools/certify_m0_pow_tiny.py --source .build/m0-pow-binomial160-v90-20261022/source/code/native_eabi_m0_pow_fast.inc --json /tmp/pow-tiny-certificate.json
python tests/m0_pow_tiny_binomial_arm_self_test.py --elf .build/m0-pow-binomial160-v90-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-tiny-arm.json
python tests/profile_m0_math_matrix.py --benchmark .build/m0-balanced-timing-v87-20261022 --owned-elf .build/m0-pow-binomial160-v90-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-tiny-matrix.json
```

No USB access was made. Hardware acceptance still requires the accepted
frozen platform/memory source, a matching immutable restore package and the
agreed explicit transfer of USB ownership.
