# E0 add/sub: exact coefficients and normal rounding cells

This is a source-level argument for the added E0 paths, composed with the
parent's normal/top/nonfinite paths. It is not a mechanically checked proof
of all ARM executions or an all-input performance theorem.

## Partition and units

Let h=2^52, q=2^-1074. A subnormal has magnitude N*q with0≤N<h. A normal
with exponent field E has magnitude M*2^(E-1)*q, h≤M<2h.
The unchanged entry computes both original sign:exponent words. A zero
field branches to the corresponding E0 stub. Thus at least one field is0;
the other field partitions into0/1, finite2..54, finite≥55, and2047.
Other operand domains retain the parent's paths.

## Both fields at most1

After clearing the signs, each raw magnitude word is exactly its integer
coefficient at quantum q. Since one field is0, a same-sign sum is less than
3h. If it is less than2h, its raw coefficient directly encodes E0 or E1,
including signed zero. If it is at least2h, it has54 bits and the E1 operand
must exist. ORing the same-sign metadata therefore gives sign:E1. The
parent's one-bit exact tie-even round shifts it once and packs at E2.
There are no lower discarded bits: this is exactly an integer sum at q.

An opposite-sign difference is an exact integer with magnitude below2h.
The copied two-word subtraction/negation chooses the larger magnitude's
sign and returns the raw coefficient. Exact cancellation returns positive
zero. Same-sign negative zeros retain their negative sign. No normalization
or rounding is required in the opposite-sign case.

## A normal operand with E≥2

Field2047 is checked before changing metadata and uses the parent's exact
NaN/Inf policy. For finite E≥55, even the smaller cell radius at a power of
two is2^(E-3)*q≥h*q. Every subnormal is strictly smaller, so the normal value
is the RNE result regardless of signs or parity. A zero subnormal returns
the other finite nonzero value directly.

For finite E2..54, the ordinary half-cell radius is2^(E-2)*q. Only a move
toward zero from an exact power of two has radius2^(E-3)*q. The cell helper
selects the latter precisely when signs differ and the normal fraction is
zero. Let its radius be2^k*q. A negative k (only the E2/power-of-two case)
cannot contain a positive integer subnormal coefficient and goes to arithmetic.

The helper compares the integer subnormal coefficient with2^k. For k<32,
a nonzero high magnitude word is necessarily too large; otherwise compare
the low word. For k≥32 it compares the sign-cleared high word times two
with1<<(k-31), and requires low word0 for equality. All shifts are bounded.
A strict smaller coefficient is inside the normal value's rounding cell.
Equality is accepted only if the normal significand's low bit is even.
Thus it returns the normal operand exactly when RNE permits that shortcut.

For remaining cases, metadata for the E0 operand is set to a virtual field1,
while its actual packed bits are left unchanged. The common unpack subtracts
only its sign and therefore retains the true subnormal coefficient without
adding an implicit bit. This exactly represents N*q at the virtual exponent.
The other operand remains a real normal with E2..54.

Same-sign addition stays normal and cannot overflow; the parent unsigned
alignment/sum/RNE kernel applies to the smaller coefficient as well. For
opposite signs and a gap≥2, the same normal-result/one-shift bound applies.
The only adjacent-exponent case is E2 versus virtualE1: its exact difference
coefficient is2*M-N≥h+1 and below4h, so it is already normal or needs the
parent's one-bit round. It cannot enter an underflowing normalizer. Metadata
used as cell-comparison scratch is rebuilt from untouched argument words
before either shared arithmetic path.

## Completeness, ABI and resources

E0 handling plus the unchanged parent's E1..54, E55..2045, E2046 and E2047
paths cover every input encoding. No C++ fallback or trap is required by
add/sub. The standalone object has no undefined symbols or relocations.
All1472 bytes of its executed public body match the full source object
without exclusions. The full object drops only mk61_m0_dadd_slow from its
dependencies and adds no helper dependency.

Every path uses the initial20-byte R4-R7/LR saved frame and matching pop.
No path calls another function, reserves extra stack, writes globals,
accesses SIO/MMIO, masks interrupts or allocates memory. The candidate was
executed as a bare ELF without mapped firmware/ROM and with only32 bytes
of permitted stack writes; the observed depth is20 bytes. These facts do
not replace whole-platform/IRQ or physical timing acceptance.

Other allocated sections and all subsequent multiply/divide bytes are
unchanged. M4/generic contributions remain unchanged. General pow and
whole-library completion are outside this delta and remain open.
