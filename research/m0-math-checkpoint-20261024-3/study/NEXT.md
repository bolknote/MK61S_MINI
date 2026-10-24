# Next implementation: use cheap directional bounds before the 119-insn kernel

Current runtime parent is the sealed `.build/m0-atan-residual-geometry-20261024`.
It has17 observed raw speed deficits, all39,548 inputs profiled in both
SIO states. Do not mutate it. The expanded diagnostic/model here covers
all ten remaining magnitudes; the full ninth-order model accepts them
all with radius3, but its117-121 instruction helper alone is too costly
for some paths. It is not integrated or a public speed result.

`path-costs.json` reproduces each actual full DIRTY count and attributes
the cost before the first fallback. Inverted input3FFA9C6244EA8335
reaches fallback at1704 vs Qfplib1819 (budget115), without calling the
residual helper. Input3FDD4F22ABBC3AA7 has already spent1699 including
the162-instruction residue helper (budget91). Blindly appending119
instructions will not meet the goal. No process from these tests remains
running. All authoritative packets and canonical sources are intact.

The following cheaper design is NOT IMPLEMENTED. Exact numerical bounds
for it are checked in `cheap-design-bounds.json`; proofs and actual ARM
execution must accompany any new runtime gates.

## 1. Keep only one small metadata word through the fast path

After the old third/fifth terms are available, compute
`r3=int32(uint32(C3)-3*uint32(T3))` in[-1,1] and
`r5=int32(uint32(C5)-5*uint32(T5))` in[-4,9].
Pack `uint32(r5+4) | (uint32(r3+1)<<4)` into one word for the inline
packer. This avoids retaining Z,C3,C7 through packing. Existing scalar
values and their RNE divisions are unchanged. The metadata adds a few
hot instructions; preserve the old four wins, which have31-55 DIRTY
instructions of margin before this metadata.

## 2. Rounded residual correction and a favorable old-polynomial gate

In a NEW child, change the inherited six-bit divider input to
`top + (den>>1)`. It computes
`floor((floor(abs(R)/2^38)+floor(den/2))/den)` with signed correction.
The error is strictly below `.5+35/2^20`, magnitude still<=33, and the
32-bit sum is safe. This is an interval approximation, not a claim that
every integer quotient is exactly rounded. Update helper tests accordingly.

All h<1/128 may attempt residue repair. Symmetric safe radii for the
old polynomial become6 at h<=1/250,9 at h<=1/160 and23 globally.
After updating the tail, recalculate `favored=(tail<half)==(negative!=invert)`.
The discarded fifth cross products and the omitted positive h^9/9
can only lower the old polynomial. Its favorable error upper bound is
therefore much tighter than its absolute error. The exact old fifth
remainder accounts for its entire coefficient and rounding bias.

Let `normal = !invert && source_e!=-6`. A sufficient extra acceptance
test after the rounded residue correction is
`favored && int32(5*distance)+r5 >= (normal ? 11 : 14)`.
The exact bounds give upper error <2.6122-r5/5 Q70 in the worst geometry,
and0.5 less in normal geometry. This resolves the low-distance direct
inputs without computing a full new polynomial. Recompute favored after
correction; do not reuse its pre-correction value.

## 3. Fast inverted residual predicate BEFORE general residue repair

For inverted geometry D is divisible by64 and N is divisible by64.
Set d=D>>6. The signed residue
`R'=(N<<58)-h*d` has magnitude<33*d<2^60. Since N<<58 is a multiple
of2^64, R' is exactly the signed64 representative of `-low_product(h,d)`.
Only the low64 product is needed: one wide32 product and two32-bit MULs.
Its absolute value is safe to compute; it cannot equal INT64_MIN.

If `abs(signed64(low_product(h,D>>6))) <= D>>7`, the original quotient
has error<=.5 Q70. For inverted h<=1/180 the unchanged old angle then
has absolute error<6.937536, so original midpoint distance>=7 is safe.
Perform this predicate before the general162-instruction residue helper.
It should resolve3FFA9C6244EA8335 within its115-instruction budget,
without a polynomial change or a general division. Prove and measure it.

## 4. Cheap ninth term for the remaining unfavorable large-h case

The expensive poly helper can be replaced on this path by an h-only
approximation. Let x=uint32(h>>47), representing h*128 in Q16.
Form q2,q4,q8,q9 by four32-bit products, each rounded with+32768 then
shift16: q2=x*x, q4=q2*q2, q8=q4*q4, q9=q8*x.
Every product plus rounding constant fits uint32. Then
`ninth=((((q9+2304)>>9)*7282U)>>16)` is exact rounding of q9/4608.
The composed floors divide by512 then9; no general division is needed.
Thirteen Q16 units of accumulated error, scaled by128/9, plus final
rounding give error<.51 Q70 versus h^9/9.

Correct only the old fifth division's known remainder:
`delta5=(r5>=3)+(r5>=8)-(r5<=-3)` and `r5new=r5-5*delta5` in[-2,2].
Add `delta5+ninth` to the reduced angle, with the same geometry sign.
No Z,C3,C7 or missing-cross recomputation is needed. Return delta and
r5new packed in one word if helpful (use unsigned shifts for negatives).

After this update a symmetric radius7 is safe. For a favorable output,
an extra sufficient test is
`15*distance >= (normal ? 35 : 42) + 5*r3 - 3*r5new`.
The exact worst-geometry upper-error base is below2.79 Q70 before
adding r3/3-r5new/5; normal geometry is0.5 tighter. This accepts the
remaining BFABB0EDC0AE5C6F case: r3=0,r5old=7,delta5=1,r5new=2,
ninth about7; the new center is about2 Q70 above midpoint. Its actual
true midpoint gap is2.86417 Q70. The packed metadata is essential to
certify this small margin without another table or119-instruction helper.

Use existing symbolic square/cube/seventh bounds from `certificate.py`.
For the old favorable bound, exclude the nonpositive omitted ninth term
and use the one-sided C5 error (no discarded-cross loss in its upper
bound). For the new ninth term include the positive omitted h^11/11
tail. `cheap-design-bounds.json` checks thresholds11/14 and35/42 exactly.
All new gates must keep the original fallback on ambiguity.

## Integration checks for the next child

Build/control must be against geometry parent ELF5cea0e75… and full
objecta68a1ad9…, not older packing/residual blobs. The parent qualification
profiles every input, so it needs no `cold-profile.json` merge when copied.
Carry the complete17-input speed list and old four successes into the
short probe, then the all-input MPFR/instruction run and generic M0/M4
isolation. Child code only, no canonical/Git/hardware action. Whole
math work, general pow totality and physical acceptance remain open.
