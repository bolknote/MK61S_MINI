# Unqualified lazy-factor pow experiment

V123 is an unfinished experiment over the qualified software candidate
[V122](../m0-pow-root-prefix-20261023/README.md). Both Clang `Os` and `O2`
variants compile and link. No correctness or performance results have yet
been collected for either variant. V122 remains the current candidate.

The prototype first constructs a bounded Q64 factor from selected repeated
roots and an integral part. It computes the 128-bit numerator lazily when
the final rounding test is ambiguous. Negative proper fractions can start
with the existing reciprocal-root seed table. Integer exponents retain the
parent path. The aim is to avoid unconditional 128-bit numerator work on
ordinary fractional powers; this checkpoint makes no claim that it succeeds.

The [complete generated C++ source](kernels.cpp), its three input fragments
and the [compile/link evidence](evidence.json) preserve the exact current
draft. The error formulas, interval acceptance and fallback behavior need
independent endpoint and MPFR checks before they can be trusted. Full matrix,
resource/isolation, cache and hardware checks are also pending. No new
coefficient table or global allocation is intended, but that has not yet
received the candidate's resource audit.

From the repository root, rebuild into a new private directory:

```sh
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-factor-20261023/build.py --parent-work .build/m0-pow-root-prefix-v122-20261023 --output .build/m0-pow-factor-checkpoint-reproduced
```

The builder requires the frozen V122 source/build/firmware, installed
Clang/GNU Arm tools and Ninja. It removes only the parent's prefix section
from a copied private object, substitutes the experimental module and
resolves the existing reciprocal-root table without adding another table.
It checks the allowed undefined imports before linking.

Diagnostic ELFs inherit the V122 build stamp and must not be installed.
Neither production sources nor the device firmware are changed by this
checkpoint. No M4 change, USB operation or push is involved.
