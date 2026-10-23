# Pow rounding boundaries and V138 measurement preparation

This intermediate checkpoint preserves the work following the
[V138 Horner checkpoint](../m0-pow-horner-20261023/README.md), build
`83CF4AC4`. It adds analysis, host prototypes, numerical evidence and a
snapshot of the math measurement harness. It changes no production source,
Cortex-M4 code, firmware image or V138 placement.

## Rounding and termination

The [dyadic-boundary report](totality/exact-boundary.json) gives a
source-bound classification of exact binary64 rounding ties. For
`x = A * 2^e` and reduced `y = s*p/q`, an odd coefficient greater than one
can produce a dyadic result only for positive `y`, with `q` dividing `e`
and `A = C^q`. A result coefficient below `2^54` bounds `p` by 34 and `q`
by 32. Powers of two and the early `x == 1` / `y == 0` cases are covered
separately. Both exact V138 recognizers passed 20,098 ARM calls over
10,049 cases. The reported write low-water includes a deliberately placed
result slot; it is not a callee stack measurement.

Directed MPFR intervals establish 18 nonzero relative gaps below `2^-114`
in 19 selected cases; 13 are actual RNE midpoint cases. The
[published 114-bit bound](https://www.vinc17.net/research/papers/ieeetc2009-powr.pdf#page=9)
has restricted hypotheses and cannot justify a universal precision limit.
All 19 public V138 pow calls still match MPFR, without reaching the final
rescue. These witnesses demonstrate neither a V138 rounding failure nor
insufficient 1,024-bit precision. General non-dyadic termination remains
unproved, and the final undecided trap remains in place.

## Exact comparison prototype and a new speed deficit

[Exact rational bounds](exact-space/active-bounds.json) restrict the
nontrivial exponent domain after tiny/huge-exponent rules. In principle,
128-bit indices and 160-bit column accumulators suffice for an integer
power-comparison circuit. This is a mathematical space bound, not a
compiled M0 stack or execution-time guarantee.

The bounded-cache host prototype passed 4,109 digit checks and 160 power
comparisons. Of 46 cost experiments, 27 exhausted their explicit work cap
and returned no numerical answer. A real midpoint example needs 64,658
limb products and 129,343 requests with a 512-entry cache, versus 8,128
products when retaining limbs. These are host operation counts, not ARM
instructions or physical cycles. The prototype is not integrated as a
firmware fallback.

The [tiny-exponent audit](exact-space/tiny-profile.json) exposes a real
performance gap outside the previous 117-group matrix. Every one of 196
owned results is the correctly rounded value 1. On the 168 normal-base
cases, all owned calls are slower: mean 40,624.21 ARM instructions versus
1,345.80 for Qfplib's `exp(mul(y,ln(x)))`. The 28 Qfplib mismatches occur
on the excluded subnormal-base cases. No tiny-exponent fix or new firmware
variant is included here.

The earlier finite matrix remains 115 faster / two equal / zero slower
groups. It does not establish speed parity for all inputs. Physical cycle
parity, a total correctly rounded general pow path and production
acceptance remain open work.

## Math measurement harness

[math-execution](math-execution/README.md) preserves the offline runner,
frozen helpers, timing fixture, producers, reports and all 120 binary input
chunks with exact oracle bits. Its original execution manifest pins 189
artifacts for V138: 119 matrix chunks covering 117 groups and 23,352 cases,
plus one mandatory 30-case public-pow canary. APP ABI/guard tests and runner
sequencing tests passed offline. Their mocked transport and timers are not
physical measurements.

Compiled firmware, APP and Qfplib binaries and copied dependency trees are
not stored in this archive. Their hashes and historical paths remain in
the original manifest. This source snapshot is not a complete standalone
hardware execution package and does not authorize device access. Physical
execution, device backups, authorization and restoration receipts are
managed separately by the coordinated transaction owner.

## Integrity and reproduction

The 163 archived originals are byte-identical copies, including the prior
offline freeze record. Historical paths and status fields are retained
without rewriting. [provenance.json](provenance.json) maps each copy to its
original; `checkpoint.json` pins every archive file.

From the repository root:

```sh
python3 research/m0-pow-boundary-20261023/verify-checkpoint.py
python3 research/m0-pow-boundary-20261023/verify-checkpoint.py --check-local
```

The second command also checks the private originals and all 189 execution
artifacts when they are available. Both commands only read files and do
not import project helpers, open USB or install firmware. Original
producers retain their recorded dependencies and write outputs beside
the script; run copies in a new private work directory when reproducing
them, preserving this archive and the frozen execution package.
