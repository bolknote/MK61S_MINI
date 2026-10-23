# Changed-branch arithmetic argument

This is an elementary source-linked proof for the proposed branch, not a
machine-checked proof of the whole runtime. Existing entry guards, near
cancellation, same-sign addition, and the IEEE fallback are unchanged.

At `.Lda_mixed_general`, `r6` is the signed difference of exponents and the
old range guard rejects |gap|≥55. The earlier exact path took |gap|≤1.
Thus the new arithmetic sees two normal opposite-sign operands with
2≤d≤54 and a normal result, guaranteed by the unchanged exponent guard.

Use the larger exponent as the unit and write the magnitudes as M and
N/2^d, with integers 2^52≤M,N<2^53. Their exact positive difference T obeys

`2^51 < M - N/2^d < 2^53`.

The normalized binary64 coefficient therefore needs zero or one left shift.
The sign is the larger operand's sign. `.Lda_unsigned_x/y` retains its packed
sign and exponent minus one, and removes the same subtrahend from the high
word to obtain the unsigned 53-bit coefficient.

For d≤32, the aligned 64-bit significand and 32-bit fractional limb encode
N/2^d exactly. For d>32, define S=N*2^(32-d), A=floor(S), and set
J=A when S=A, otherwise J=A|1. The far paths compute exactly this J.
When S is not integral, A<S<A+1 and J is the odd endpoint of that unit
interval. Thus S and J are strictly on the same side of every even integer;
neither is an even integer. In the 32-fraction-bit representation all
rounding midpoints for coefficient quantum 1 or 1/2 are multiples of 2^31
or 2^30. The normalization boundary is also an even integer. Replacing S
by J preserves the normalization choice, all midpoint comparisons and ties.
When S is integral no replacement occurred. This proves the sticky reduction
preserves RNE for both possible normalization shifts.

`negs r4,r4; sbcs low,other_low; sbcs high,other_high` forms unsigned
96-bit M*2^32-J: NEG's carry is one exactly when no fractional borrow is
needed. No signed negation or magnitude test is required after subtraction.
The optional `adds/adcs/adcs` shifts all 96 bits once and decreases the packed
exponent by one unit. No significant high bit can be lost by that shift.

The common round step increments on a set guard bit. If all sticky bits are
zero it clears the retained LSB after incrementing, which is tie-to-even.
Carry from the retained low word is propagated. Adding the saved packed
sign/exponent-minus-one to the normalized high significand packs the result;
an RNE carry across a binade is represented naturally by that addition.
The original guards exclude subnormal-result and overflow handling here;
such inputs retain their original fallback path.

The changed path has no BL, literal pointer, SIO access, global write or IRQ
mask operation. Its only memory writes are the unchanged entry push of
R4–R7/LR, 20 bytes, followed by the matching pop. The registers outside the
volatile set are either unchanged or saved/restored as before. Public EABI
argument/result layout and the separate subtraction sign-flip entry remain.

This argument establishes the changed arithmetic path's mathematical result
and source-level resource behavior. Targeted ARM/oracle/profile evidence is
stored separately. It does not establish universal speed versus Qfplib,
whole-firmware stack/IRQ bounds, physical cycles, or general pow totality.
