# Directional residual and ninth-order atan repair

This child retains the parent's selector, reciprocal, first polynomial,
tables, public ABI and fallback. It changes only the RP2040 atan repair,
adds one small inverted-residue predicate, and inlines a short ninth term.
All gates accept only a complete interval inside one binary64 rounding
cell. Ambiguity still reaches the original refinement.

## Parent domain and exact division remainders

The fast domain is1/64<=abs(x)<=64. The pinned parent proof gives h<2^63
in Q70, hence h/2^70<1/128, and exact numerator/denominator quotient
error below33 Q70. The existing operand bounds are Z<2^56,C3<2^49,
C5<2^35,C7<2^22. D>=2^58 in every geometry.

The existing third kernel is exact nearest division by3. If a=hi*2^32+lo,
write hi=3*qh+rh and lo=3*ql+rl. Since2^32=3*0x55555555+1, the floor
quotient is qh*2^32+rh*0x55555555+ql+floor((rh+rl)/3). The old kernel
forms this value and increments it only when the final remainder is2.
The magic coefficient0xAAAAAAAB=ceil(2^33/3) computes both32-bit floor
quotients exactly. Thus r3=C3-3*T3 is in[-1,1].

For the old fifth T5=floor(((C5>>3)*0xCCCCCCCD+2^30)/2^31), the positive
coefficient error is below.4 and the rounding error at most.5. Including
the discarded three bits gives r5=C5-5*T5 in[-4,9]. Low32 subtraction
recovers these small signed remainders exactly. One metadata word stores
uint32(r5+4)|(uint32(r3+1)<<4). Integer operands and q remain unchanged.

The seventh divisor is also exact nearest division by7: its coefficient
satisfies2454267027*7-2^34=5. With C7<2^22, the positive coefficient
error is below the rational1/7 gap. Its rounding remainder is in[-3,3].

## Rounded71-bit residual

The inherited helper computes R=(N<<64)-h*D modulo2^71. Since
abs(R)<33*D<2^70, its signed representative is exactly R. The existing
three wide32 products and one low32 high-high product remain exact.

Set top=floor(abs(R)/2^38), den=floor(D/2^38)>=2^20. This child divides
top+floor(den/2) by den using the same bounded six-bit Thumb divider.
The signed correction has magnitude<=33 and error strictly below
.5+35/2^20 Q70. The32-bit rounded numerator fits. If it is below den,
the exact bounded quotient is zero and the six division steps are skipped.

Reusing the original polynomial after the linear quotient correction
contributes at most33*(hcap+33/2^70)^2. The worst sum of table and optional
denominator-halving errors is1 Q70. The non-inverted exponent classes-5
through-1 use only.5 table error. Exponent0 exact input1 is conservatively
assigned to the wider class; this cannot weaken correctness.

The old symmetric intervals give radii6 for h<=floor(2^70/250),9 for
h<=floor(2^70/160),23 globally. Exact bounds are in `certificate.json`.

## Favorable direction of the old polynomial

The discarded fifth cross products are nonnegative losses. The omitted
positive h^9/9 atan term also lowers the old seventh-order polynomial.
Let E3 and E7 be the inherited symmetric cube/seventh errors, and E5+
the one-sided positive fifth error without those discarded cross losses.
The polynomial's upper error is bounded by

`E3/3 +1/3 +E5+/5 -r5/5 +E7/7 +3/7`.

After quotient, table/halving and derivative errors, the exact upper base
is below2.612161-r5/5 Q70, and.5 lower in the narrow ordinary geometry.
For a center above midpoint with positive polynomial sign, or below it
with negative sign, this upper error determines the needed rounding side.
The code recomputes this direction after applying the residual correction.
Its sufficient integer gate is5*distance+r5>=11 (ordinary) or>=14 (wider).
No approximation table or floating arithmetic is involved.

## Short ninth term and fifth division correction

Let x=uint32(h>>47), representing h*128 in Q16. Four32-bit products form
q2,q4,q8,q9, each rounded with+32768 then shifted16. Each product plus
rounding fits uint32. Starting with at most one Q16 unit of input loss,
the errors after the squares/products are at most2.5,5.5,11.5,13 units.

The integer `((((q9+2304)>>9)*7282)>>16)` is exact rounding of q9/4608.
The nested floors divide by512 then9; all resulting integers are<=132,
where the multiplication implements exact floor division by9. The total
ninth-term error is at most2317/4608<.51 Q70 versus h^9/9.

For v=r5+7 in[3,16], q5=(v*13108)>>16 is exact floor(v/5). Therefore
delta5=q5-1 rounds r5/5, and r5new=v-5*q5-2 lies in[-2,2]. The inline
POD returns delta5+ninth and r5new separately, avoiding an unnecessary
encode/decode round trip. Only these integer corrections modify the tail.

The ninth-order symmetric error is below6.722859 Q70: radius7 is safe.
Its favorable upper-error base is below2.789538+r3/3-r5new/5 Q70 and.5
lower in the narrow ordinary geometry. Integer gates15*distance>=35+
5*r3-3*r5new (ordinary) and>=42+5*r3-3*r5new (wider) are sufficient.
The positive omitted h^11/11 tail is included. The old favorable gate
excludes the nonpositive omitted ninth tail; their signs differ deliberately.

## Inverted low64 predicate

For inverted geometry both N,D are divisible by64. Put d=D>>6. Then
R'=(N<<58)-h*d is exactly R/64, with abs(R')<33*d<2^60. Since N<<58 is
a multiple of2^64, low_product(h,d) is the signed64 representative of
-R'. One wide32 product and two32-bit cross products compute it exactly.

The unsigned shifted test `low_product(h,d)+(d>>1)<d` accepts a safe
subset of the signed interval[-floor(d/2),floor(d/2)]. Every returned
true therefore certifies abs(H-h)<=.5 Q70. It may conservatively decline
an equality boundary. For h<=floor(2^70/180), the unchanged polynomial
and two tables then have error<6.937536 Q70. Original distance>=7 is
safe, without a general quotient correction. The predicate runs before
the more expensive residual helper and preserves SIO.

## Packing, execution binding and scope

Repair starts within54 Q70 units of midpoint. The quotient correction
is at most33 and the ninth/fifth correction at most16. Since half-quantum
is at least1024,54+33+16<1024 preserves the original quantum, binade and
retained significand. Only tail and rounding increment change. A center
exactly on a midpoint fails all new gates. The original fallback remains.

`helper-proof.json` checks the actual71-bit ARM helper against unbounded
Fraction quotients. `extra-helper-proof.json` checks the ninth term against
Fraction(h**9,9*2**560), its remainder against exact division by5, and the
inverted predicate against unbounded signed residuals. It also checks the
exact original third kernel on boundary/carry/random49-bit values. Its
inline-source wrapper has separate register allocation; the public caller
is tested and bound independently. Every helper call checks ABI, bounded
writes and both SIO states without firmware or ROM mapped.

`isolation.json` compares every other allocated section, tables, undefined
dependencies and generic M0/M4 controls. `public-body-proof.json` confirms
an independently recompiled/relinked whole component ELF matches exactly.
`qualification.json` supplies fresh MPFR answers and actual instruction
counts for every input in the expanded public corpus, with raw Qfplib
outcomes retained. Instruction counts do not establish physical cycles,
whole-library completion, mixed-image integration or hardware acceptance.
