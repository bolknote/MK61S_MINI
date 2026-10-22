# Reuse the first checked pow approximation on RP2040

V98 is an isolated, unpromoted prototype over V93. It sends an ambiguous
normal-result approximation directly to the existing independent integer
midpoint checks, avoiding the Q94 logarithm/exponential prepass when those
checks succeed. The approximation remains an untrusted hint. All rounding,
domain and error guards retain their previous acceptance rules.

The [report](evidence.json)
pins source, ELF, inputs, ROM, test programs and results. The
[four-file patch](first-seed-pow.patch) applies over the V93 integer/dyadic
patch and its recorded earlier dependencies. ROOT production math and the
physical PicoCalc firmware are unchanged.

## Instruction results

| Difficult stream | Cases | V93 instructions/call | V98 instructions/call | Original Qfplib instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 3,141.33 | 2,407.95 | 1,501.55 |
| Near one, large exponents | 5 | 1,501.20 | 1,496.80 | 1,573.80 |
| Moderate bases/exponents | 128 | 5,209.95 | 3,041.99 | 1,535.45 |

The two remaining slow streams use 23.3% and 41.6% fewer instructions than
V93. They still use more instructions than Qfplib. The reference is composed
as `exp(mul(y,ln(x)))`, since the pinned Qfplib has no standalone pow. It
differs from MPFR on 63, 5 and 71 cases in these three streams; owned results
have zero mismatches.

The full unchanged matrix has 117 groups, 119 chunks and 23,352 inputs:
113 groups use fewer instructions than Qfplib, two tie and two remain slower.
No non-pow instruction group changes. Several ordinary pow groups improve;
the wide-exponent control grows by 0.27 instructions/call and remains below
its Qfplib reference. These are executed ARM instructions on identical emulator
instances using captured RP2040 ROM code, with owned functions from the V98 ELF and Qfplib
from the pinned V87 diagnostic. They are not physical timings or a universal
speed guarantee.

## Implementation and bounds

The bounded tiny-integer helper decodes its exponent and packs its accepted
result with 32-bit operations. Exact mask identities prove the same integer
predicate and quotient as the old 64-bit code. The exact wide product and
overflow/threshold checks remain. Every accepted intermediate fits 32 bits.
This reduces the helper from 288 to 248 bytes and frees 40 scratch bytes.

The first-candidate call uses pointers to the caller's live double parameters
plus the 64-bit hint, fitting the standard four-register ABI. It copies those
parameters synchronously, performs the existing integer midpoint checks and
returns the identical old refinement on every decline. The pointers are
neither retained nor modified. A by-value prototype exceeded the unchanged
scratch limit by 64 bytes and was rejected by the linker; no image from that
attempt was installed.

A dedicated normalized 128-bit square avoids duplicate cross products.
Three exact 32x32-to-64 products reconstruct its leading 64-bit square; one
cross-high term is added twice. The result, exponent and propagated radius
are identical to the old generic aliased product. The general multiplication,
midpoint inequalities, exact sqrt-cube logic and all existing RNE guards remain.
The source-rewrite certificate checks these differences against frozen V93.

## Qualification and placement

Final V98 checks pass with zero rounding errors:

- 10,379 specialized squares match the old full product byte-for-byte and
  independently enclose exact rational endpoint squares. Counted samples
  average 292.5 instructions versus 425.5 for the generic product.
- 5,219 tiny-integer cases match the qualified parent, including all decline
  behavior and canaries; 1,671 accepted results independently match MPFR.
- 14,451 first-candidate calls over 2,065 pairs handle correct, adjacent,
  distant, random and invalid hints; 27 calls use aliased parameter pointers.
  Every result matches MPFR and all parameter bytes/canaries remain intact.
- 10,020 exact-power midpoint comparisons and 10,298 accepted untrusted hints
  over 3,412 dyadic pairs; 111 public pow/MPFR integration calls.
- All 265,409 ARM/MPFR calls across twelve functions, all 23,352 matrix cases,
  and the complete 75,229-entry potentially affected subset selected from the
  1,003,177-case pow corpus. The older full-million run belongs to V86 and is
  not relabeled as a V98 run.

Cortex-M4 soft/hard O3 output and generic non-RP2040 ARMv6-M allocated output
remain identical to their established baselines. Four other numerical objects
and allocated relocation targets are identical to V93. All source differences
are confined to four pow includes; 3,845 other frozen source files are identical.
Of 224 inspected non-pow linked functions, 221 keep their addresses and bytes;
the three unchanged RAM shift routines move by 24 bytes.

The scratch reservation remains 4,096 bytes; actual use is 4,088. The new
candidate veneer is checked against the previous canonical 16-byte veneer
body and its linked target. Main static RAM remains 198,856 bytes, heap 30,520
and image extent 1,537,008. Allocated Flash grows by 760 bytes over V93. There
are no new tables or global allocations, and no linked libgcc archive members.

Thirty-eight real instruction/data traces compare 19 streams per image under
four explicit warmed cache models. Their instruction totals match the separate
matrix. Only the two hard pow streams change modeled misses, both improving;
the other 17 streams match. These models exclude physical cache policy,
prefetch, IRQs and other-core traffic, and do not replace device timings.

Two hard pow instruction gaps remain. General pow totality outside the exact
stage's 224 exponents remains unproved, and the final undecided interval trap
is retained. Finite tests do not establish an all-input precision bound. The
return-value contract is RNE; errno and floating exception flags are not added.

## Reproduction

Prepared candidate: `.build/m0-pow-square-kernel-v98-20261022`.

```
python tools/certify_m0_pow_first_seed.py --source-root .build/m0-pow-square-kernel-v98-20261022/source --baseline-root .build/m0-pow-square-cube-v93-20261022/source --json /tmp/pow-first-seed-certificate.json
python tools/certify_m0_pow_tiny32.py --source .build/m0-pow-square-kernel-v98-20261022/source/code/native_eabi_m0_pow_fast.inc --json /tmp/pow-tiny32-certificate.json
python tests/m0_pow_first_candidate_arm_self_test.py --elf .build/m0-pow-square-kernel-v98-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-first-seed-arm.json
python tests/m0_pow_square128_arm_self_test.py --elf .build/m0-pow-square-kernel-v98-20261022/firmware/mk61s-picocalc-pico-h.elf --baseline-elf .build/m0-pow-first-pointers-v96-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-square-arm.json
```

No USB access was made. Production integration and physical acceptance still
need the final accepted frozen platform/memory source, a matching immutable
restore package and explicit USB release after the agreed peer windows.
Qualification respected the shared release freeze and only wrote owned
research/build artifacts. A subsequent explicit user request authorizes a Git
checkpoint of these patches, evidence and checks, with the numerical status
updated to V98. This does not promote the candidate into production or authorize
device access.
