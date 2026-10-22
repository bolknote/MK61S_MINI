# Checked integer and dyadic pow refinement on RP2040

V93 is an isolated, unpromoted prototype over V90. It adds bounded
integer-product refinement for small integer and dyadic exponents, preserving
the existing RNE guards and full fallback. ROOT production math and the
physical PicoCalc firmware are unchanged.

The [report](../../doc/measurements/m0-pow-integer-dyadic-v93-20261022.json)
contains source/ELF/test/ROM hashes and complete qualification results. The
[four-file patch](integer-dyadic-pow.patch) applies over the V90 binomial
patch after the V87 checked-pow patch and its earlier dependencies.

## Instruction results

| Difficult stream | Cases | V90 instructions/call | V93 instructions/call | Original Qfplib instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 15,686.77 | 3,141.33 | 1,501.55 |
| Near one, large exponents | 5 | 1,491.60 | 1,501.20 | 1,573.80 |
| Moderate bases/exponents | 128 | 15,125.58 | 5,209.95 | 1,535.45 |

The two slow streams improve by 80.0% and 65.6%. They still use more
instructions than Qfplib. The reference is `exp(mul(y,ln(x)))`, since the
pinned Qfplib has no standalone pow. It differs from directed MPFR on 63,
5 and 71 inputs in these respective streams; the owned implementation has
zero mismatches.

The full unchanged matrix has 117 groups, 119 chunks and 23,352 inputs:
113 groups use fewer instructions than Qfplib, two tie and two remain slower.
These are executed ARM instructions on identical emulator instances using
the captured RP2040 ROM. Owned functions use the production V93 ELF; Qfplib
uses the pinned V87 diagnostic. They are not physical cycles or a universal
speed guarantee.

## Arithmetic

Small integer powers use normalized 128-bit mantissas and a binary
exponentiation chain. Exact high products omit a positive tail below three
mantissa units. A propagated integer radius covers this tail, operand errors
and normalization. Zero low-word cases have tighter bounds; the first square
of a binary64 significand is exact. Positive results are accepted only when
their binary64 rounding cell is unambiguous. Reciprocal candidates are
independently checked against both exact midpoint boundaries.

For `|y|=p/q`, `p<=32`, `q` a power of two through 128, the existing Q94 result
provides an untrusted search hint. Integer enclosures compare `x^p` with
`midpoint^q`; for a negative exponent they compare their product with one.
Strictly separated intervals determine a side. Two neighboring boundaries
certify a unique RNE cell. A wrong or distant hint cannot bypass these checks.
An overlapping enclosure retains the original CORE/refinement/rescue path.

The largest certified propagated radius is 28,864, below 2^15 normalized
mantissa units. The source-pinned rational certificate covers multiplication
tails, exponentiation-chain bounds, one-bit exponent alignment and exponent
widths. Exact boundary ties normally decline. For positive `y=3/2`, an exact
106-bit square can certify a proposed binary64 square root. If its square
equals `x`, one final IEEE multiplication computes `x*sqrt(x)` with RNE,
including midpoint parity. This avoids an expensive logarithm/exponential
fallback on exact sqrt-cube ties. No rounded-double square equality is used.

## Qualification and placement

The final V93 ELF passes:

- 6,000 independently checked exact-rational interval products, including
  aliased squares; 11,309 direct integer/inverse-power inputs and 390 public
  MPFR calls.
- 3,412 dyadic input pairs, 10,020 exact-power midpoint comparisons,
  10,298 accepted untrusted hints and 111 public MPFR calls. The corpus includes
  generated exact dyadic roots and exact midpoint cases.
- The existing 14,180-case binomial test with 10,393 accepted helper results.
- All 265,409 ARM/MPFR calls across twelve functions and all 23,352 matrix inputs.
- All 75,229 selected entries covering every potentially affected numerical
  path in the published pow corpus: 24,855 integer, 49,587 noninteger dyadic
  and 787 binomial-gate entries. The selector scans all 1,003,177 entries and
  records source line ranges and hashes. This is a complete selected subset,
  not a newly claimed full-million V93 run.

Cortex-M4 soft/hard O3 output and non-RP2040 ARMv6-M allocated output remain
identical to their established baselines. Four other numerical objects and
their allocated relocation targets are identical to V90. Every prior native
function except `pow_small_integer` and `pow_refine_checked` retains its object
instruction bytes. Of 224 inspected non-pow linked functions, 221 keep both
address and bytes, two differ only by equivalent BL relocations, and the shared
log-ratio entry moves by 40 bytes with equivalent instructions/targets.

Allocated Flash grows by 3,560 bytes over V90. Main static RAM remains 198,856
bytes, heap 30,520, scratch reservation 4,096, and image extent 1,537,008.
There are no new tables or global allocations. The scratch object payload is
identical; every changed linked RAM call/veneer is checked against an equivalent
target. The existing rsqrt seed payload moves by 32 bytes.

Thirty-eight actual ARM instruction/data traces cover 19 streams per image,
including every ln/log10 stream, sqrt, tan, conversion and pow controls, and
the three hard pow streams. Their instruction totals match the independent
matrix. Four explicit cache models compare warmed XIP accesses. These models
do not establish physical cache behavior or timings. Fifteen control streams
have identical modeled misses; the exact-exponent pow control grows from zero
to 0.0078–0.0195 misses per call across the models. All three difficult pow
streams have fewer modeled misses. The report records each model and trace.

Two hard pow speed gaps remain, as does the general pow totality proof outside
the existing exact stage's 224 exponents. The final undecided interval trap is
retained. Finite tests do not establish an all-input precision bound. The
return-value contract is RNE; errno and floating exception flags are not added.

## Reproduction

Prepared candidate: `.build/m0-pow-square-cube-v93-20261022`.

```
python tools/certify_m0_pow_integer128.py --source .build/m0-pow-square-cube-v93-20261022/source/code/native_eabi_m0_pow_integer128.inc --dyadic-source .build/m0-pow-square-cube-v93-20261022/source/code/native_eabi_m0_pow_dyadic128.inc --json /tmp/pow-integer-certificate.json
python tests/m0_pow_integer128_arm_self_test.py --elf .build/m0-pow-square-cube-v93-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-integer-arm.json
python tests/m0_pow_dyadic128_arm_self_test.py --elf .build/m0-pow-square-cube-v93-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-dyadic-arm.json
python tools/select_m0_pow_refinement_corpus.py --corpus .build/m0-pow-totality-20261020/pow.wc --output /tmp/pow-affected.wc --json /tmp/pow-selection.json
```

Nothing was flashed or accessed over USB. Hardware acceptance still requires
the final accepted frozen platform/memory source, its matching immutable restore
package and explicit USB release after the agreed peer windows.
