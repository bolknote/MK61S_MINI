# Low normal exponents and nonfinite add/sub paths

This is a source-level arithmetic/guard argument for the private delta,
not a machine-checked proof or whole-library acceptance. Existing normal
and top-exponent paths are reused, not numerically changed.

## Dispatch

The original entry still rejects exponent field0 for either operand into
the old C++ fallback. At the common guard, R6=(maxE-55) mod2^32, R7=1991.
The taken BHS has exactly three classes: equality for maxE2046; a negative
CMP residual for normal maxE1..54; positive residual1 for maxE2047. BNE
keeps the top path as before. BPL distinguishes nonfinite from low-normal
without modifying the original packed arguments or R4/R5 sign:exponents.

## Low normal inputs

Same-sign addition cannot underflow, and maxE≤54 cannot overflow. Its
established unsigned alignment/sum/RNE kernel is therefore valid even for
E1 and is entered at its unchanged start.

For opposite signs with exponent gap≥2, the nonzero result exceeds half
the larger binade and remains normal. Both inputs are normal, maxE≤54,
minE≥1: the gap is2..53. The unchanged unsigned difference kernel can be
entered after its redundant far-gap check. Its first instruction overwrites
R7, so skipping the ADD/CMP/BHI does not remove any required state.

Equal/adjacent exponents produce an exact integer magnitude N at quantum
2^(Ebase-1075), with Ebase≥1. The copied subtraction chooses the larger
magnitude's sign; exact cancellation returns positive zero. A54-bit N
uses the original one-bit tie-even round step and raises Ebase by one.
No smaller coefficient loses any bit.

For a coefficient requiring left normalization, the maximum allowed shift
before exponent1 is b=Ebase-1. The new loop shifts at most b bits; each
shift decreases both b and the encoded exponent equally. The sign bit in
the encoded exponent therefore cannot borrow away. Shift choices16/8/4
retain the original width guards, and additionally require enough budget.
If the budget is smaller than such a safe chunk, the required normalization
is larger than the budget: shift exactly b once and pack at exponent1.
All shifts are bounded and no significant bit is discarded.

The common pack is `N + ((E-1)<<52)` with the retained sign. For normalized
N this is the ordinary encoding. At E1, an N below2^52 directly encodes
a subnormal; an N at least2^52 encodes a normal. Since N*2^(Ebase-1) is an
integer multiple of the minimum subnormal, this boundary needs no further
rounding. This covers normal inputs whose exact difference is subnormal.
The loop either reaches the hidden bit or consumes its strictly decreasing
budget, so it is bounded and cannot normalize past E1.

## Infinity and NaN

At least one exponent field is2047 in the new nonfinite entry. The three
operations `(packedE<<21) ASR21; +1` produce zero exactly for that field,
independently of the sign. Fraction tests inspect all52 fraction bits.

A NaN in A is returned with its quiet bit set, preserving its payload/sign.
Otherwise a NaN in B takes precedence over infinities and is quieted.
A single infinity is returned; same-sign infinities return A; opposite
infinities return the existing positive canonical quiet NaN. These are the
project's existing D::add rules, including the dsub sign flip of B. The
integer RNE and MPFR oracles check the IEEE class/result; raw NaN policy
also matches the unchanged parent exactly on all qualified cases.

## Resources and unaffected paths

The new paths add no BL, MMIO/SIO access, global writes, heap, IRQ mask or
workspace. The only added data are two IEEE literal words in the text
pool (quiet-bit mask and canonical NaN), not a lookup table. The existing
20-byte fast frame and24-byte E0 fallback frame are unchanged. R4-R7 are
restored by the original pops; R8-R11 are not used.

The ordinary and top input paths are unchanged in source/control flow.
Object controls preserve every other allocated section and all following
multiply/divide bytes; undefined dependencies are identical. The full
public body matches the executed diagnostic body except its pinned old
fallback BL. M4/generic contributions remain identical. Full firmware
integration, IRQ/platform stack acceptance, physical cycles and general
pow totality are not established by this delta.
