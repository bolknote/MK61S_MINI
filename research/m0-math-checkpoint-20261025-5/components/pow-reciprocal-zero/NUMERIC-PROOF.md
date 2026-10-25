# Preserve known zeros without changing reciprocal rounding

The private entry still requires R0=0, R1=0x3ff00000, with any binary64
denominator in R2:R3. Guards, tiny overflow, fallback classes, seed and NR
arithmetic remain inherited. This is not a general division entry.

At the second unsigned product, both R0 and R4 are exactly zero. The first
product sets R4=0 and leaves the raw numerator low word R0=0 intact. Swap
R0 and R4 as the macro's temporary: R0 was not an input, output or other
temporary in the old multiplication. This is an exact register permutation
from equal input states, so all other registers and flags agree. R4 now
remains zero and R0 receives the old scratch value. The wrapper checks the
unchanged live product outputs and preserves the complete frame.

The xH*a0 multiplication uses dead R1 instead of R4. The next existing
LSLS R1,R3,#7 overwrites that temporary. With R4 still zero, the reconstruction
LSLS R4,R0,#5 is unnecessary. SUBS R0,R4,R2 consequently computes exactly
the same signed residual. At the following join every R0-R7/R12/SP/NZCV
value and the complete28-byte frame agree; no approximation has changed.

R4 stays zero through signed correction. Its normalization doubling is
therefore unnecessary. The next LSRS replaces NZC before any use, and the
removed LSLS never changed V. Both quotient branches retain the same exact
midpoint and guard/carry behavior.

The remainder certificate now uses dead R3 instead of R6. Its first read of
R3 follows its first write, so the old R3 value is irrelevant. Every numeric
instruction, flag and decision is unchanged; the uint32 certificate proof
and complete fallback remain valid. The old MOVS R6,#0 before rounding
continues to execute, so R6 remains zero on a decisive certificate path.

Upward rounding ADD lowword; ADC highword can use that zero R6 and omit the
old MOVS R2,#0. ADD overwrites carry before ADC. The deleted R2 value is
overwritten by LSLS R2,R1,#31 before use. The inconclusive path performs the
old full multiplication, which clobbers R6; it explicitly restores R6=0
before joining upward rounding. The negative path needs no restoration.
At pack, all live values and flags agree; dead R3/R6 are not read before
callee-saved registers are restored. The exact rounding decision and all
returned bits are identical to the parent for the entire private contract.

Cost saving equals the number of second products, plus zero doublings,
plus decisive positive corrections. No input can gain instructions from
this transform. The original20,994 input/flag cases and both SIO states are
rerun, with separate fresh MPFR public controls and an expanded scan of all
65,536 seed divisors using two complete-mantissa patterns. These finite
measurements do not prove universal Qfplib speed parity or device cycles.
The full source permutation proof establishes equivalence to the parent;
general pow totality and unrelated operations remain separate work.
