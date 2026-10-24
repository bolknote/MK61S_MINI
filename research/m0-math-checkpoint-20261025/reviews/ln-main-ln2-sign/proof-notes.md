# Scope

Frozen child661ae2b6 / ELF9f872b40 changes only the two main packer
upper predicates plus a compile-time constant assertion. Exact parent is
Q77source84213d8e / ELF1164948d. Q77's original local conditional receipt
1c2a3bdb is reused together with explicit parent-chain closure d5bb1166
and its accepted main/cold component receipts54dc555c and005774ca.
This is a private delta verdict, not whole-public-ln,507, shipping,
canonical or hardware acceptance.

# Sign and exact multiplication

The actual included tables contain
L70=818323753292969962226 and
L94=13729194366926868337785367782. An independent64-term rational
atanh(1/3) series, with rigorous positive geometric tail bound,
confirms both constants' RNE and
epsilon=L70-2^70*ln2≈-0.47236478351691485, strictly between -1/2 and0.
No producer generator or certificate function was executed to obtain this
enclosure. The integer difference L94-(L70<<24)=7924966 also exceeds
the Q94 half-unit uncertainty. Source static_assert checks the exact
corresponding high/low order; it adds no executable bytes.

The actual positive-normal entry admits exponent1..2046, so
k=-1022..1023 and n=abs(k) is0..1023 (negative k only reaches1022).
For either sign, the logarithm magnitude is n*ln2 plus or minus log(m).
The source forms n*L70 exactly through two32×32 products, concatenation
and explicit carry. Multiplications and carry sums fit their uint64 /
uint32 domains; no rounding is introduced. Thus the exponent contribution
to magnitude error is n*epsilon, strictly negative when n>0, for either
output sign. This is the necessary magnitude argument; multiplying the
signed ln2 error by k directly would give the wrong reasoning for k<0.

# New acceptance proof

The unchanged accepted polynomial operation bounds are
Eexact=7.897372764676165<8 and Eraw=13.400120688467078<14 Q70 units.
The former is also independently recovered from the inherited raw bound
by replacing the generic argument term A/(1-hmax) by1/(1-hmax), with
hmax=1/2048; all other source operation bounds remain exact.

Let M be the approximate magnitude and T the true magnitude. With
polynomial bound E and exact table error epsilon,
M-T lies strictly inside [-E+n*epsilon_low, E+n*epsilon_high].
If M is above the relevant midpoint by d>=8exact or14raw, then
T-midpoint>=d-E-n*epsilon_high>0. The negative table error therefore
cannot send the true magnitude below this midpoint.

The predicates apply only inside the old guards. Their greatest possible
distances are7+ceil(n/2) exact and15+ceil(n/2) raw. For every integer
n1..1023 the full lower error endpoint gives true position strictly below
the next midpoint, whose distance from the current one is at least2048
in this packer's minimum shift11. The worst reaches are1010.1265463exact
and1023.6292943raw, safely below2048. At a binade carry the next gap only
increases. Negative outputs use the same magnitude RNE symmetry.

The n0 exact call passes error8, and raw call passes exponent_error0,
so neither receives the shortcut. The inherited near call uses error4,
also excluded. Below-midpoint, midpoint, threshold-minus-one and old
outer-guard paths preserve their old predicates. All source shifts are
inherited11..27, half>=1024, and guard<=527; half+14 cannot overflow.

# Source, artifacts, execution

An exact source reconstruction accounts for just the two predicates and
the static assertion. Both inline bare pack fragments equal production.
The two changed allocated function sections grow8bytes each; all other
code, Q77 near body, tables, BSS, ASM and dependencies are byte-identical.
All39 external bindings match the actual pinned resident (memory aliases
use the real wrapped symbols). Complete CPP/ASM objects and entire private
ELF plus bare unit were independently rebuilt byte for byte, with no body
or ELF exclusions. Static-assert and pre-assert objects/ELF are equal;
old probe calls are not added to qualified counts.

Own controls:234 public ARM calls (39 raw inputs×READY/DIRTY×candidate /
accepted parent/Qfplib) with fresh MPFR4.2.2;424 bare pack calls covering
212 abstract configurations, including40 uses of the new shortcut.
There are240 independent Fraction RNE endpoint checks. n0, both signs,
threshold-minus-one, below-midpoint, midpoints, old guard edges, parities
and binade carries are present. Abstract bare points are interval tests,
not claims of actual polynomial evaluations at arbitrary x/h metadata.
All calls check PCS/SP/bounded writes and SIO. Bare SIO accesses are zero;
bare stack44B. Public subset stack504B does not replace author640B.

The fixed raw5FFA5B2647E9E2C7 agrees with MPFR and loses its fallback in
both states: READY595/DIRTY655 vs parent2238/2333 and correct Qfplib776.
All three remaining raw deficits and all seven parent regression rows
were replayed and retained. Recounting saved120988 states (not rerunning
them) retains118044 parent counts, gives1fixed/0new and3raw deficits
remaining. Five states regress3instructions, two regress4. This is no
whole-parent speed win or physical-cycle claim.

No normal builds, CI, device, Git, lease, canonical/source promotion or
reviewed-count mutation occurred. Original reviewed coverage stays298/507.
