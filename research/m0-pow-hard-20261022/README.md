# Current difficult-pow audit (V80)

The V79 flash-memory composition passed all 1,003,177 entries of the saved
CORE-MATH `pow.wc` corpus against directed MPFR RNE bounds. Its result digest
matches the older complete V51 run. This is a complete run of that finite
corpus, not a proof for every binary64 pair.

The earlier 114-group timing matrix omitted difficult pow streams. Three
additional finite streams from the saved corpus expose remaining instruction
count gaps. Unit bases are excluded from this additional selection:

| Stream | Cases | V79 mean instructions | Qfplib composition |
| --- | ---: | ---: | ---: |
| Regular exponents | 128 | 27,507.414 | 1,501.547 |
| Near one, large exponents | 5 | 3,784.600 | 1,573.800 |
| Moderate bases | 128 | 25,597.273 | 1,535.453 |

All owned results are correct on this selection. Qfplib is the original
pinned `ln`/multiply/`exp` composition and does not satisfy RNE on many of
these cases. Instruction counts do not measure physical execution time.
These streams must be included in the continued speed audit; the former
112-faster/two-equal result applies only to the original prepared matrix.

A mixed-mode Unicorn counter regression was also reproduced: cached code
first executed without a code hook could later bypass counting. Counted
calls now flush all translated code. The seven-operation regression check
passes. Replaying the always-counted matrix and all additional hard cases
gives identical per-case counts to the earlier profiles. Numeric results
were unaffected. The complete V79 corpus ran before this counter-only
change; the exact source versions used are preserved under `source-used/`.

Results, encodings, hashes and limitations are recorded in
`doc/measurements/m0-pow-hard-audit-v80-20261022.json`. General pow totality
outside the exact stage's 224 exponents is still unproved. Its undecided
trap is retained, and hardware timing remains pending.
