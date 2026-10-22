# Checked pow refinement on RP2040

V87 reduces the remaining expensive pow fallbacks without changing the RNE
acceptance tests or Cortex-M4. It is an isolated, unpromoted prototype on the
unaccepted 7AEA platform/memory parent. Nothing from this experiment was
flashed onto PicoCalc.

The complete evidence is in
[`m0-pow-checked-v87-20261022.json`](../../doc/measurements/m0-pow-checked-v87-20261022.json).

## Instruction comparison

The expanded standard comparison has 117 groups, 119 chunks and 23,352 exact
operand/result triples: 113 groups use fewer instructions than the original
Qfplib, two tie, and two remain slower. The first 114 groups retain their
previous vectors. The additional difficult inputs are saved in
[`hard-pow-inputs.json`](hard-pow-inputs.json); the builder independently
revalidates every expected result with directed MPFR.

| Additional pow stream | Cases | V81 instructions/call | V87 instructions/call | Qfplib instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 27,507.7 | 19,006.6 | 1,501.5 |
| Near one, large exponents | 5 | 3,784.6 | 1,474.2 | 1,573.8 |
| Moderate bases/exponents | 128 | 23,545.5 | 15,114.8 | 1,535.5 |

All five saved near-one cases individually use fewer instructions than Qfplib.
The reference computes `exp(mul(y, ln(x)))`, since this Qfplib has no standalone
pow. It differs from MPFR on 63, 5 and 71 cases in these respective streams;
the owned implementation has zero mismatches. These are executed ARM
instruction counts with the captured RP2040 ROM, not physical timings or a
universal speed guarantee.

## Implementation and bounds

An undecided Q94 result enters CORE-MATH's integer refinement directly. Its
128-bit, exact-boundary and 256-bit tail is extracted verbatim into one shared
body, including every rounding guard and the final owned rescue. Earlier
special/domain exits keep the full CORE entry. The internal caller has a
positive normal base and a checked logarithm-product range comfortably inside
the integer tail's error bounds. The vendor generator and provenance reproduce
both files from the same pinned upstream bytes, retaining the MIT notices.

For `f=|x-1|<=2^-26` and `D=ey-clz(f*2^62)` in `[3,6]`, the new path forms the
exact Q80 linear term of `y*ln(x)`, then bounded quadratic, cubic and quartic
corrections. The rational error certificate proves a radius below five Q80
units; the code reserves eight. Flooring to Q64 has error below two units, so
the original checked fast exp body can accept it. An ambiguous cell keeps the
Q94/CORE/rescue path. The first tier is skipped only where its unchanged error
test necessarily rejects it. No table is added.

Relative to V81, allocated Flash increases by 2,576 bytes. The image extent
remains 1,537,008 bytes, main static RAM 198,856, heap 30,520, and the existing
scratch reservation 4,096. All 274 ordinary math inputs retain their addresses;
every pre-existing read-only coefficient payload is identical. Two shared
log-ratio helpers move by 56 bytes, and long-call veneer slots may be permuted.
The link check accounts for each changed non-pow branch and checks equivalent
targets. This does not claim identical XIP traffic.

Thirty-eight actual ARM instruction/data traces compare 19 streams per image,
including every ln/log10 stream. All 16 control streams have identical miss
counts under the four explicit cache models; only the three difficult pow
streams change, with fewer modeled misses. Replacement/fill policies are model
assumptions, not measurements of the device.

## Qualification

The algorithm parent V86 passes the complete 1,003,177-case pow corpus with
zero errors and the same result digest as V80. V87 changes only placement:
all five numerical object payloads and allocated relocation targets match V86,
and every one of the 23,352 per-case result/instruction digests is identical.
The complete million-case run is attributed to V86, not relabeled as V87.

The final V87 ELF separately passes 265,409 ARM/MPFR calls across all twelve
functions, 4,489 exact-rational argument enclosures, 3,417 domain declines,
352 public pow checks, and direct production 512/1024-bit interval tests with
real linked memory and ROM code. Forced-caller tests also exercise both rescue
precisions and their sign/stack ABI. Cortex-M4 soft/hard O3 output and generic
ARMv6-M output remain identical to their established baselines.

General pow totality is still unproved outside the exact stage's 224 exponents.
An undecided 1024-bit enclosure still traps. Finite testing does not establish
an all-input precision bound. The return-value contract is RNE; errno and
floating exception flags are not implemented.

## Review and reproduction

[`checked-pow.patch`](checked-pow.patch) is the ten-file delta over frozen V81,
after the V77 arena and V81 exact-short-power patches. Applying it to a private
copy reproduces every changed file exactly; the other 3,837 source files are
identical. One whitespace line in the copied upstream MIT/header preamble is
retained verbatim. ROOT production math and peer-owned CMake/memory work are
unchanged.

The prepared candidate is `.build/m0-pow-stable-v87-20261022`, and its diagnostic
is `.build/m0-balanced-timing-v87-20261022`. The report pins source, ELF, test,
ROM, input and reference hashes. The diagnostic preserves all production math,
RAM initializers and original Flash bytes except the documented integrity
extent/footer fields; APP ABI and CRC/bounds checks pass.

The new fixture is selected with:

```
--comparison-set all --hard-pow-profile research/m0-pow-checked-20261022/hard-pow-inputs.json
```

Useful independent checks, with the repository's ARM/MPFR Python environment:

```
python tools/certify_m0_pow_near.py --source .build/m0-pow-stable-v87-20261022/source/code/native_eabi_m0_pow_fast.inc --json /tmp/pow-near-certificate.json
python tests/m0_pow_near_argument_arm_self_test.py --elf .build/m0-pow-stable-v87-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-near-arm.json
```

Physical acceptance waits for the platform's reproducible cold-start USB fault
to be fixed, then the agreed memory window and explicit USB release. A future
hardware diagnostic must use the final accepted frozen source and its matching
immutable restore package; the provisional diagnostic is not installation
authority.
