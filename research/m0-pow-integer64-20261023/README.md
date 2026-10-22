# Experimental Q64 prepass for negative integer pow

This checkpoint preserves an unfinished V111 experiment over the qualified
[V110 software candidate](../m0-pow-small-cross-20261023/README.md). V110
remains the preferred candidate. The [patch](experimental-pow.patch) changes
only the private RP2040 pow dispatch and declarations; the standalone
[kernel source](kernels.cpp) supplies the experimental implementation.
No production source, device firmware or M4 implementation is changed by
this research checkpoint.

## Current results

| Difficult pow stream | V110 instructions/call | Experimental Clang Os | Qfplib composition |
|---|---:|---:|---:|
| Regular exponents | 1,813.22 | 1,746.02 | 1,501.55 |
| Near one, large exponents | 1,496.00 | 1,497.40 | 1,573.80 |
| Moderate bases/exponents | 2,003.52 | 1,999.35 | 1,535.45 |

These are executed ARM instructions on the existing 259 hard inputs, with
captured RP2040 ROM and modeled SIO division. They are not physical cycles.
Qfplib is compared as `exp(mul(y,ln(x)))`; that composition does not meet
the required correct rounding on every input in these streams.

The earlier GCC cached variant passed the complete 23,352-input matrix,
with 113 groups faster than Qfplib, two equal and two slower. It reduced
ordinary negative-integer pow from 854.22 to 757.90 instructions, but
increased the negative-wide stream from 861.97 to 913.28. That tradeoff is
preserved in the evidence. Its complete matrix must not be attributed to
the later Clang Os image, which has only the focused checks below.

## Algorithm and checks

Normalized 64-bit centers carry explicit error radii. An exact first square
initializes the interval; bounded square/base products raise it to integer
powers from 3 through 32. The reciprocal is only a seed. One midpoint
product can certify neighboring cells in the same binade. Strictly
ambiguous cases retain the existing 128-bit refinement.

A new guarded two-cell lemma permits one exact midpoint comparison when
the complete interval limits the answer to the two neighboring numbers.
It requires radius at most 511 and excludes a binade-start cell. The
maximum composed power radius is 5,702; larger ambiguities use the original
arbitrary-hint path. No approximate result is accepted solely from a seed.

The saved [algebra certificate](algebra.py) binds the inspected GCC
[reference](reference.inc). All four interval cores are identical in the
Clang source after linkage spelling changes; the entry adds a necessary
exponent guard and calls the same owned leading-zero helper.

Independent exact-rational and directed-MPFR checks on the Clang Os ELF
passed 6,000 square endpoints, 6,000 exact-base product endpoints, 6,000
packed distances, 23,570 cached neighbors and 1,013 complete two-cell
interval checks. Of 7,609 power inputs, 6,561 were accepted correctly and
1,048 declined. Hooks checked 6,561 exact first-square states and 693 new
trusted-cell calls; 246 complete public pow calls also matched MPFR.
Every ARM call checks the ABI and bounded writes.

## Reproduction and unfinished work

The [report](evidence.json) preserves the exact sources, ELF hashes, full
focused reports, earlier matrix and tuning results. Reproduction needs the
frozen V110 source/build directory and existing tools recorded there:

```sh
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-integer64-20261023/reproduce.py --parent-work .build/m0-pow-final-parent-v110-20261023 --output .build/m0-pow-integer64-reproduced
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-integer64-20261023/algebra.py --include research/m0-pow-integer64-20261023/reference.inc --json .build/m0-pow-integer64-reproduced/algebra.json
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-integer64-20261023/endpoint-arm.py --elf .build/m0-pow-integer64-reproduced/diagnostic.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json .build/m0-pow-integer64-reproduced/endpoints.json
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-integer64-20261023/profile-hard.py --elf .build/m0-pow-integer64-reproduced/diagnostic.elf --json .build/m0-pow-integer64-reproduced/profile.json
```

The output directory must be new. The reproducer copies the frozen source,
applies the patch, recompiles the caller and experimental kernels, and links
against the pinned parent objects. Clang is a tool for this experiment;
adoption would require a frozen GNU assembly implementation and equivalence
checks, without adding a firmware compiler dependency.

The diagnostic ELF inherits the parent's build stamp and must not be
installed. Complete matrix/corpus qualification, source/link/resource and
M4/generic isolation checks, cache modeling, physical timings and an
acceptable ordinary-input tradeoff remain pending for this prototype.
Both difficult instruction gaps and general pow termination remain open.
There are no new tables in the prototype. This checkpoint does not claim
production readiness or all-input correctness or speed parity.
