# Private1/x: exact overflow endpoint and register-only seed

The hidden reciprocal entry retains the actual caller contract R0=0 and
R1=0x3ff00000, denominator R2:R3 any binary64. No general ddiv caller or
default M0/M4 code changes. The sole root source call is unchanged; its BL
is relinked because the private entry moves. Every dynamic entry checks
the numerator, return address and eight-byte-aligned entry SP.

For a positive subnormal denominator d=k*2^-1074,1/d=2^1074/k. Binary64
RNE overflows at B=2^1024-2^970. Let T=2^50. Exact integer multiplication
proves T*B<2^1074<(T+1)*B. Since the product k*B increases with k, every
integer1<=k<=T yields infinity and every k>T is beyond the fast predicate.
The latter retains the original IEEE fallback. Zero separately yields
infinity; negative zero/subnormals copy the denominator sign. The ARM
predicate compares the sign-stripped high word to2^18, then requires low
word zero only at equality. It is exactly the full52-bit comparison k<=T.
All other invalid exponent classes retain the old fallback with two extra
instructions; non-tiny subnormals have eight or eleven extra instructions.
These parent cost increases and all Qfplib comparisons are preserved.

For guarded inputs the numerator sign is zero, so divisor bit31 directly
supplies result sign. This removes two instructions in both general and
short-dyadic paths. Powers of two already use exact exponent scaling and
do not change. Hardware retains its nine independent ALU instructions
between starting SIO division and reading the quotient.

The exact table seed is now inlined with register allocation:
R6 quotient, R1 D17, R4 temporary and R7 exact signed residual. R0,R2,R3,R5,
R12 and SP are untouched. This preserves numerator low word zero, both
packed divisor words, x1 and exponent/sign context without save/call/return.
The arithmetic and128-entry256B table are unchanged. The previous finite
proof gives estimate-floor(N/D) in[-1,3], where N=2^32-1. Thus one upward
correction suffices and downward correction repeats at most three times;
each preserves qD+r=N until0<=r<D. The unit wrapper uses the same macro and
table as production, covers all65536 divisors and all16 NZCV at table edges,
and verifies all live registers. Its wrapper stack/speed is not a production
performance claim. The old standalone312B seed is no longer allocated.

After q conversion u0=(q+1)>>1, reciprocal Newton and remainder calculations
are unchanged. R1 and R7 differences are dead before fresh definitions in
the next long product. R0..R7,R12,SP,NZCV and28 saved bytes agree at the
after-second-product join. All four186B suffixes are byte-identical. DIRTY
SIO is never written and all seven words remain intact. The new inline SP
is exactly entrySP-20, not the outer Machine SP. No nested C ABI call occurs
at that four-modulo-eight stack depth; the old standalone seed call remains
eight-aligned in the control. Final callee-saved/SP/PC contracts hold.

All direct records, including wrong Qfplib outputs and parent cost increases,
are retained. No nominal-domain filter is used. Normal public root calls are
all guarded in the actual complete corpus, audited without removing inputs.
Their measured savings equal two instructions per product visit plus four
per software seed (five for the old one-step-up seed case).

The first direct-driver import failed before scalar/MPFR calls because it
used older generic control labels. Initial nested public trace runs stopped
after318 completed calls, two partial aborts and23 MPFR evaluations because
the test asserted entrySP-20 against the outer Machine SP. The runtime and
its isolated scalar tests were correct; the relative trace assertion was
fixed. Those preflight calls are separately preserved and excluded from
qualification. Historical producers must not run inside frozen directories.

The wider goal is open: remaining scalar deficits, other needed math speed,
general pow totality, source merge/relink and actual integrated R12/loader/
layout guards, the14B old-overlay hazard, physical cycles and release remain.
