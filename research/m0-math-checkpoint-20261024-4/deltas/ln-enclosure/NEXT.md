# Remaining work after the strict-radius child

The full expanded corpus has31 correct-Qfplib losses in READY and34 in
DIRTY (34 raw inputs/65 state rows). It exposed more preexisting inputs;
do not reuse the old13-input short-probe count. All losses and every
parent +1-instruction regression must remain visible. IEEE +/-0,+Inf
still use the old cold entry; a separate unqualified prototype exists in
../m0-ln-cold-entry-20261024. Its old entry classifier added1..6 normal
instructions. A six-instruction exponent range check against2046 may
reduce that overhead, but needs actual full replay after integration.

28 remaining inputs use the near-one interval. The separate study
../m0-ln-near-directional-analysis-20261024 has exact one-sided rounding
remainder bounds and28 actual product54 calls. With

    r2=z-2*ceil(z/2), r3=cube-3*third, r4=fourth-4*quarter,
    s=+1 for odd+even, -1 for odd-even,
    bias12=-4*r3-s*(6*r2+3*r4),

the upper/lower uncertainty bases are1.9598178414<2 and2.1850118974<9/4.
The proposed gates12*distance-bias12>=24 or+ bias12>=27 accept13/28.
The exact reduced quotient remainder

    r=(delta<<21)-h*(8192+signed_n)

fits signed low32. Substituting its known signed input error reduces
bases to1.420755103<3/2 and1.645949159<7/4; weighted gates accept15/28.
Neither is implemented. Exact-midpoint cases need an explicit rounding
decision, and model_bits is wrong on two declined inputs. Do not return
the old rounded q unconditionally or substitute Qfplib without a proof.

Further options: retain fractional parts of the existing square/cube/
fourth products and signed h remainder to estimate the polynomial error.
Its omitted fifth term is negative in both log(1+h) and -log(1-h), and
can be approximated by four small Q16 products. The near table contains
only Q70 centers; no matching higher-precision near table was found.
A small fractional-center correction table would need a separate size/
accuracy justification and directed rational/MPFR proof; none exists yet.

The three extra DIRTY inputs are3FEF7FFFFFFFFFE6/E8/EA, just outside the
old near lower boundary. All are general-kernel quotient cases. A general
small-low-limb seed family, rather than input-specific branches, may help:
for signed low limb ell in[-32,32], write delta=F*2^32+ell, F<=512.
Compute floor(F*R/2^14) by four exact16x10 MULS/carries. For ell>0 add
floor(ell*(R>>32)/2^14); for ell<0 subtract that floor and2. The seed is
below H with error<5, so at most four unit comparisons recover floor(H).
All products/remainders fit32-bit limbs. This proposal is not implemented
or qualified. It should preserve READY and reuse the existing table.

The full math goal remains open: other operations, general pow totality,
combining reviewed deltas on the repaired base and physical acceptance.
