# Small-h lower enclosure for atan

This child changes one acceptance gate in the sealed directional/ninth
parent. The selector, exact dyadic reduction, reciprocal, polynomial,
residual helper, tables and fallback are unchanged. Only RP2040 uses the
new gate; generic M0/M4 allocated compile controls remain byte-identical.

Put S=2^70 and c=1/512. The inherited product bounds give

    Ez=1/2+13/512
    E3=1/2+13/512+c*Ez
    E5=1/2+c^2*E3+c^3*Ez+E3*Ez/S
       +(2^17-1)*(S*c^2+Ez)/S+(2^24-1)*(S*c^3+E3)/S
    E7=1/2+c^2*E5+c^5*Ez+E5*Ez/S
       +7*(S*c^2+Ez)/S+(2^24-1)*(S*c^5+E5)/S.

These bound the actual C3,C5,C7 errors in Q70 before division by3/5/7.
The old kernels have exact signed division remainders r3 in[-1,1] and
r7 in[-3,3]; the stored r5 is C5-5*T5 in[-4,9]. Consequently, if P7 is
the original seventh-order reduced polynomial,

    P7-atan(h/S)*S > -E3/3-E5/5-E7/7-3/7-S*c^9/9+r3/3-r5/5.

The negative ninth-order remainder is bounded by S*c^9/9 using the
alternating atan series. No new ninth term is evaluated for this gate.
It runs after the parent's rounded residual correction, whose error is
strictly below1/2+35/2^20. Reusing the old polynomial adds at most
33*(c+33/S)^2 through the derivative. Normal exponents-5..-1 have table
error at most1/2; the wider (halved/inverted) class has at most1.

Adding all terms produces the exact lower-error base B:

    Bnormal=1.9006899104742208... <29/15
    Bwide=2.4006899104742208... <37/15.

The complete exact fractions are in low-certificate.json. Thus the
reduced center's error is strictly above -B+r3/3-r5/5. When the center
is below the midpoint with positive polynomial sign, or above it with
negative polynomial sign, it safely remains on that side whenever

    15*distance+5*r3-3*r5 >=29 (normal), or >=37 (wide).

The implementation tests h<2^61, a subset of h/S<=c. It stores r3+1 in
the existing metadata, so the equivalent thresholds are34/42; this
avoids subtracting1 at runtime. Finite exact checks in certify-low.py
verify this encoding identity over every remainder and relevant distance.
All arithmetic fits32 bits. Midpoint distance0 cannot satisfy this gate
within the proven remainder ranges. The inherited retention argument
still applies: only the corrected low tail changes, within the original
quantum/binade, and all uncertain cases use the original refinement.

The new gate has no helper calls, new data or SIO access. Isolation checks
every other allocated section, undefined dependencies, all tables and the
generic/M4 controls. Public full-object recompilation and whole component
relink match exactly. All116,376 public state cases are separately run
against fresh directed-MPFR references and profiled; all106,312 retained
parent counts reproduce. Helper rational/ABI/SIO contracts are replayed
for the new ELF, with the original transcripts. These checks establish
this private delta's scope, not a combined-library or physical-cycle GO.
