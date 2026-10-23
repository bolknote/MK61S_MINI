# Finite exponent2046: arithmetic, guard and frame argument

This extends the independently reviewed private mixed-sign implementation.
It is a source-level argument, not a mechanically checked proof of ARM or
the whole runtime. The current diagnostic ELF is bound to the full public
assembly object by `body-equivalence.json`.

## Guard partition

The existing entry checks reject exponent field0 for either operand. R4/R5
retain each original sign:exponent. R6 subsequently contains
`(max(Ea,Eb)-55) mod 2^32`.

The new comparison is against1991 with BHS. Values below1991 are exactly
the old normal fast domain55≤maxE≤2045. On the taken branch CMP's flags are
unchanged: Z is set only for maxE=2046. BNE therefore retains the old fallback
for low-normal inputs and maxE=2047, including every Inf/NaN. Zero/subnormal
entry checks jump straight to the fallback, without reading those CMP flags.

Thus the only added mathematical domain is two normal finite inputs with
maxE2046. All ordinary arithmetic bodies and their instruction counts remain
unchanged. CMP's old/new carry difference at maxE2045 is overwritten before
any arithmetic uses it; the following sign XOR supplies the sign-branch N flag.

## Opposite signs

A nonzero difference of two normal operands with maxE≥55 remains normal.
For equal/adjacent exponents, the smallest exact nonzero grid step is at
least2^(maxE-1076)≥2^-1021. For larger gaps the difference exceeds half the
larger binade. The difference is at most the larger operand's magnitude,
so it cannot overflow. Exponent2046 therefore satisfies the same requirements
as the earlier mixed-sign implementation; its signed/unsigned arithmetic
and RNE paths are reused without changes.

## Same signs at the top exponent

The separate path copies the established unsigned alignment/sum/increment
operations. The larger operand's saved packed addend R12 is always
`sign | (2045 <<20)`. Unlike the ordinary path, this addend is never increased.

An extra leading coefficient bit after addition means a coefficient≥2^53,
hence a sum≥2^1024. Its RNE binary64 result is necessarily signed infinity;
normalization and discarded bits cannot change that. The leading-bit test
sets R5=1. Shifting it left21 and ORing with R12 changes exponent2045 to2047,
retains the sign, and leaves all fraction bits zero. R0 is cleared.

Without that initial leading bit, the unchanged guard/sticky increment and
tie-even logic round the coefficient. A second leading-bit test before pack
also catches a carry caused only by rounding. This includes the exact
overflow midpoint: the max-finite coefficient is odd and rounds up to the
even virtual coefficient2^53. If the bit is clear, the coefficient stays
finite in exponent2046 and the original pack operation is valid. No NaN can
be produced from finite same-sign inputs.

The two Y-larger sites emit the original ADD/ADC/leading-bit/guard block
locally. Carry-normalization and round-down avoid one unconditional jump;
round-up adds the explicit jump to the unchanged increment label and retains
the same path count. Operands, flags and scratch state at every shared label
are identical to the original block. The ordinary kernel is not duplicated
or changed; only the top path uses those expansions.

## Frame and isolation

The initial R4–R7/LR push is still20 bytes. The fallback replaces SUB SP,#4
with PUSH R3 and replaces ADD SP,#4 plus POP R4–R7/PC with POP R3–R7/PC.
The callee receives the same registers and an eight-byte-aligned SP24 bytes
below the caller. The new store initializes only the previously reserved
alignment word. The six-register pop restores R4–R7 and the original return
PC in the same order; R3 is volatile under this arithmetic EABI. Frame depth
and the old C++ call target do not change. One saved instruction offsets the
extra guard branch on unchanged low-normal/Inf/NaN fallbacks; direct
zero/subnormal fallback paths save one instruction.

The new top path uses only registers and the existing20-byte saved frame.
There are no new helper calls, global writes, tables, SIO operations or IRQ
mask instructions. An explicit four-byte boundary at the block's end keeps
all subsequent multiply/divide code and literal displacements byte-identical.
That alignment-only source fix did not change the executed diagnostic ELF.

Object controls preserve all other allocated sections, undefined dependencies,
and the generic M0/M4 contribution. Full platform/IRQ stack acceptance,
physical cycles and production integration remain separate. General pow
totality is unchanged and is not certified by this work.
