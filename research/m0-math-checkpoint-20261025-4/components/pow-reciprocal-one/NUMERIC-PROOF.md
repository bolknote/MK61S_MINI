# Private exact numerator-one reciprocal

This entry is named mk61_m0_reciprocal1 and is hidden. Its precondition is
R0=0,R1=0x3ff00000: exactly positive binary64one. R2:R3 may be any binary64
denominator. It is not a general ddiv ABI or a replacement of other resident
division callers. The actual root call loads zero into R7, moves it to R0,
and loads the verified0x3ff00000 literal into R1 immediately before BL,
with no intervening entry label. Every dynamically executed public call is
also checked against this contract and its one expected return address.

For exponent E of the denominator, the old guarded division accepts normal
E in[1,2046] and0<=2044-E<=2043 because numerator exponent is1023. This is
exactly1<=E<=2044. The new guard compares E-1 to2043 and supplies the same
R6=2043-(E-1)=2044-E. Sign and fraction bits do not affect this predicate.
Every rejected input retains the original unmodified IEEE C++ fallback and
raw R0..R3, including subnormals, zero, infinity, NaNs and near-underflow.
The truth table covers all2048 exponents. The guard saves11 instructions
on accepted inputs,12 for E2045/2046 and5 for E0/2047.

In a guarded numerator-one call, normalized y0 is exactly2^31. For any
uint32 reciprocal u1, the old long multiply forms P=2^31*u1, then doubles
the low/high result. Its low word becomes0 and high word becomes u1,
including the low-word carry. MOV R5,R6 and MOVS R4,0 therefore reproduce
both live result words exactly. The old first-product temporary R2,R3,R7
and incoming flags are overwritten before use by the following long
product. This removes15 executed instructions in both hardware and software
routes, including the dyadic reciprocal route. After the second product,
R0..R7,R12,SP,NZCV and all28 saved stack bytes are identical in the actual
old/new code. The remainder and RNE suffix is byte-identical from there.

In the software route, normalized numerator R1 and y0 R4 are dead: R1 is
overwritten by the second product and R4 by the exact first-product result.
Removing their six unpacking instructions changes no live input. Two R0
constant-preparation instructions before the seed are also dead because
the seed's first instruction overwrites R0 from D. The312B seed code/table
is unchanged, preserving exact initial quotient and R12. These eight
instructions are removed only from the software route. Hardware retains
its original nine independent ALU instructions between starting SIO division
and reading its quotient; the simulator checks the same latency contract.

Every actual scalar/public delta is checked against the exact formula:
guard savings +15 per first-product visit +8 per software-seed call.
SIO DIRTY state is never written and all seven words are preserved. The
software seed call remains8-aligned. Other ddiv callers, root code bytes,
table values, scratch4080 and default M0/M4 controls remain unchanged.
The private code section shrinks1168->1060B (-108B), without new tables,
global RAM or libgcc dependencies.

The first product-only prototype passed102144 ARM calls,12734 MPFR inputs
and34 sNaN policy shortcuts before the equivalent guard and dead-unpack
changes. It is preserved in the separate frozen v1 directory and is excluded
from final qualification. The initial full/fresh drivers then stopped on a
missing R6 import in a trace hook. Their44+264 completed calls, two partial
aborts and23 oracle evaluations are preserved separately and excluded. No
kernel or numerical fault caused those trace failures. Final reruns are
separate. All raw Qfplib outputs, correct/incorrect flags and costs remain
in the actual direct/public records; no nominal-domain filter is used.

This is author qualification of a private caller component. General pow
totality, remaining needed math speed, production source merge/relink,
actual integrated R12/loader/layout checks, the14B old-overlay hazard,
physical cycles and release remain open. The full goal is not achieved.
