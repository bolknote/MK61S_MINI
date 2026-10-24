Private RP2040 directed exp enclosure and77-instruction product. The accepted
source parent is the frozen dyadic/79 component, independently reviewed by
c6aef2f9. All previous numerical paths, error radii, endpoint and IEEE returned
value policies are retained. This proof concerns the new normal error4,
tail511, positive-input, negative-displacement branch only.

Write S=2^64. The source's signed reduced integer is R<0, m=-R, and |R|/S<=h,
where h=12912720851596686/S. Let Z=m^2/S and z be the compensated square.
The accepted square certificate gives -1<=Z-z<1. Let v=2^44*(r/6+r^2/24+r^3/120) and T its integer approximation. Re-evaluating
the original rational coefficient certificate gives |v-T|<2.497143741<5/2.

For a negative residual T<=0 for every integer m in the protected domain.
For t=0 the quadratic and fifth terms are0. For t=1,2 the quadratic is0
and linear>=1. For t>=3 the source inequalities give quadratic<t/3<linear;
certify.py checks the exact small-t upper and the worst large-t ratio.
The fifth term is nonnegative and is subtracted, so it cannot violate T<=0.
Also v<0 and1/2+v/2^44>0 throughout this domain.

With M=-T, the source displacement is
 D=R+floor(z/2)-floor(z*M/2^44).
Combining the square error with its parity term gives
 (Z-z)*(1/2+v/2^44)+(z mod2)/2 <1.
The negative floor of z*M contributes no positive truncation error to the
true-polynomial-minus-D direction. Consequently
 S*p5(r)-D <1+(5/2)*z/2^44,
where p5(r)=r+r^2/2+r^3/6+r^4/24+r^5/120.
The positive sixth-and-higher Taylor remainder has the original rational bound.

Positive input with D<0 implies R<0 and n>0. A nonnegative R has only
nonnegative polynomial terms and cannot yield D<0. For n0 the scaled input
is nonnegative. Thus e>=-11 and the input's Q64 scaling is exact; unsigned
modular subtraction selects the unique small signed residual certified by
the original inverse/segment bound. Put
 f=((n*exp_step_low) mod2^32)/2^32.
The exact reduced argument differs from R/S by (epsilon-f)/S, with
|epsilon|<n/2^33. Monotonicity and the accepted |r_true|<1/1400 bound give a
one-sided reduction contribution at most
 (n/2^33)/(1-1/1400)-f*(1-1/1400).
The sixth-order Taylor bound plus the first term is strictly below1/256 Q64
units. Therefore the true exponential displacement E satisfies
 E-D <1+(5/2)*z/2^44-f*(1-1/1400)+1/256.

The source obtains a cheap curvature upper bound from b=-D. Since
 b>=m-z/2>=m*(1-h/2)-1/2,
and the unsigned modular H=1-high32(D)=1+ceil(b/2^32), g=ceil(H/1024) implies
 b+1/2<g*2^42 and m<g*2^42/(1-h/2).
It follows that z/(g^2*2^20)<6/5. The certificate checks a slightly larger
exact rational bound, including the square's unit error and the smallest g.
Thus (5/2)*z<3*g^2*2^20. The source computes
 curvature=ceil(3*g^2/2^16),
 f8=floor(256*f), sub=max(f8-1,0),
 D8=257+curvature-sub.
Because1/1400<1/256, sub/256<=f*(1-1/1400), and D8/256 is a strict positive
upper bound for E-D. All products, additions, signed conversions and shifts
are bounded in certify.py; g<=2939 and no unintended integer wrap is used.

Let A be the existing Q62 table value and P the rounded retained13-term
product. q=A-P is not doubled when error4 holds. The retained product's low32
bits are0. Its next32bits F are final after column3, immediately before the
rounding shift. The new leaf additionally returns this exact F in R12.
If rho=(F>>31)-F/2^32, then
 P-A*b/S <=rho,
because the three omitted partial products are nonnegative. This directed
bound avoids adding their absolute-error allowance to the upper side.
The ordinary scalar P is unchanged for every raw argument pair.

The accepted adaptive certificate gives A/S<(floor(q/2^48)+24)/65536.
The existing Q94 table gives B0=delta32/2^32, with table uncertainty<2^-33.
The table-bias exponential cross term plus that uncertainty is<1/256 Q62
units. Both512-entry tables and every signed bias are independently
re-certified by exact512th-power inequalities in this packet.

The true scaled result V consequently obeys
 V-q < (D8/256)*top/65536+B0+rho+1/256,
 top=floor(q/2^48)+24.
The source evaluates a strict integer Q8 upper:
 effect=ceil(D8*top/65536),
 upper=effect+floor(256*B0)+ceil(256*rho)+2.
The two units cover the bias's upward integer quantization and the strict
table cross bound. If upper<=256, V<q+1. The unchanged radius4 excludes the
previous midpoint q-1023, so the unchanged normal pack returns exact binary64
RNE below the midpoint. Equality of the integer upper with256 is safe because
the real enclosure is strict. Undecided cases retain the previous refinement.
Index0 cannot enter: a nonzero negative correction would normalize to error6;
a zero correction leaves tail0. Its arbitrary unused R12 value is irrelevant.

The source-bound literal ARM unit tests all g bins, all q-head bins and signed
bias/product-rounding admission edges against an independent unrounded rational
enclosure, not another copy of the source integer expression.275672calls,
215856accepted/59816rejected,0unsafe. Full public exp is separately checked
against directed MPFR, including wrong-Qfplib outputs and both SIO states.

The product optimization is a bijective renaming of arithmetic temporaries:
old r0/r1 scratch become r5/r6, and old r5/r6 accumulators become ABI r0/r1.
The first multiply writes r4 directly, removing its copy; the accumulators
already occupy return registers, removing the two final copies. MOVr12,r4
adds one instruction, so79->77. Its location precedes LSLSr4,1; it changes no
flags or arithmetic. Argument loads, saved-register addresses,36-byte frame,
SP epilogue and final POP are unchanged. The active body158->154B, with14
nonexecuted outside NOP bytes retaining the same168B slot and later symbols.
The mathematical register-renaming argument covers all raw arguments and
initial flags; independent raw-pair and all16NZCV tests confirm P/PCS/F.

R12 is an additional private result, not part of the ordinary scalar C ABI.
The source's zero-byte global hidden marker binds the asm output definition
to a point in the actual linked object. verify-private-return.py is REQUIRED
after every changed release build. It proves that the actual Flash veneer
restores r0/SP and tail-jumps to the RAM producer without changing LR, and
that every post-call path reaches the marker without a call or R12 write.
In this release object there are exactly two STR instructions in that window.
The producer returns directly to the original caller, so no return veneer can
overwrite F. The marker adds no instructions, table or RAM. The component
builder runs this guard automatically. This is a compiler/object-dependent
contract; it is not a portable multiple-return extension to a C prototype.
Integration must install and rerun the guard against its actual linked image.

All other RP allocated bytes/semantic relocations, selected genericM0/M4
objects, existing tiny/refinement functions and prior IEEE policies retain
their evidence. Independent review, combined integration, physical cycles and
remaining whole-goal numerical/totality requirements are not granted here.
