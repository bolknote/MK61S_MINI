# Exact seed continuation for guarded binary64 division

The public clone preserves all original normal-input and result-exponent
guards, dyadic paths, IEEE C++ fallback, hardware latency block, Newton
steps, exact-remainder correction and final packing. Only the DIRTY branch
changes: it transfers to the software copy of the guarded general path.
The continuation is private, not a public ABI: it requires the existing
20-byte saved frame, original raw operands and guarded R6 exponent addend.

Let D = (0x100000 | fraction_high20) >> 4. The unchanged normal guard implies
65536 <= D <= 131071. The hardware path calculates
q = floor((2^32 - 1)/D), then u0 = floor((q + 1)/2).
The software path performs the same two operations with the exact seed17.

The seed starts from Q=1, R=131071-D. The 17 leading numerator bits are
all ones and D lies in the declared range, so 0 <= R < D. For each of the
remaining fifteen one bits it forms T=2R+1, appends the quotient bit T>=D,
and subtracts D if required. The invariant processed_prefix = Q*D+R and
0<=R<D is preserved. T fits in 18 bits. CMP sets carry, the conditional
SUBS preserves the selected quotient carry, and ADCS appends it. At exit
the processed prefix is 0xffffffff and Q is its exact integer quotient.
Incoming NZCV is not consumed. The seed writes only R0/R2/flags and leaves
R12 intact; it has no memory or stack writes.

At the first reciprocal multiplication, R0..R6, R12, SP and the entire
20-byte saved caller frame match the READY hardware path. R7 is temporary
and is overwritten by the first long-product macro before it is read.
The first ASRS establishes carry and the following ADDS establishes carry
and overflow before any flag-dependent control flow in the common tail.
The hardware and software tails are byte-identical through return. Thus
the same approximate quotient, exact midpoint remainder and RNE result
follow for every guarded input, rather than a new approximation bound.
All other IEEE inputs keep the previous fallback, including subnormals,
overflow/underflow, signed zero and the existing quiet-NaN policy.

The software save set contains five words, including unused R7 as alignment
space. Together with the existing five-word saved frame this gives an
eight-byte-aligned SP at the seed call. Its POP restores the four packed
operand words before the common tail. A DIRTY operation reads only the CSR
before transfer, does not write any divider register, and preserves all
seven existing SIO words. The READY branch executes the unchanged sequence;
the additional bridge is not taken.

The actual source-built diagnostic ELF changes only the root reciprocal BL
at its existing address and adds a private division section. Other ddiv
callers still use the original resident function. Existing code, R12 table
consumer contracts and the 4080-byte scratch reservation are not overlaid.
The diagnostic clone duplicates the existing 32-byte dyadic constants;
there are no new mathematical table values. The new section is 1050 bytes,
which includes the duplicated guarded hardware body and software tail.
Production integration must merge and relink sources and rerun the actual
integrated consumer/loader/layout checks; this packet is not that integration.

The 67354-pair direct test is unit/calibration evidence. It includes all
65536 seed divisors with exact integer/dyadic expected results and a fresh
directed MPFR subset. All 936 wrong Qfplib state variants are preserved in
the saved subset rows; the exhaustive seed portion has no wrong Qfplib
outputs. Per-divisor Qfplib speed comparisons are not claimed for the
exhaustive portion, whose per-case timing rows were not retained. Public
pow qualification separately preserves every reference output and cost.
