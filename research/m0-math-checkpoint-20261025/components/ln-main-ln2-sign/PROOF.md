# Direction of the Q70 ln2 error

Private RP2040 child of the frozen Q77 near-ln packet. Only two main-ln
packing guard predicates change. A compile-time assertion and the exact
table certificate require the Q70 ln2 constant to be a strict lower bound.
All existing polynomials, products, quotients, constants, tables and the
Q77 near function are unchanged.

The actual constants are L70=818323753292969962226 and
L94=13729194366926868337785367782. Their difference after scaling is
L94-(L70<<24)=7924966. The Q94 constant is independently certified by
the exact100term rational log-series enclosure. Even its lower half-unit
bound exceeds L70<<24. certify.py also checks the stronger direct rational
lower-series bound, so L70-2^70*ln2 is strictly negative. The static_assert
checks the corresponding high/low-word order, preventing accidental reuse
of this optimization after a sign-changing table regeneration.

For exponent k, n=abs(k), the main result magnitude is n*L70 +/- logm.
It forms n*L70 exactly using the existing word products and carries. For
both exponent signs the exponent-table error in this magnitude is
n*(L70-2^70*ln2)<0. The polynomial error is symmetric and below7.897373
Q70 units for the exact floor(H)+1 argument, below13.400121 for the raw
reciprocal seed. Their existing certificates are inherited unchanged.

If the approximate magnitude is already above a binary64 midpoint by
at least8 (exact argument) or14 (raw), this negative exponent error cannot
move the true magnitude below the midpoint. The new shortcuts apply only
inside the original uncertainty guards and only for n>0. Their maximum
midpoint distances are7+ceil(n/2) and15+ceil(n/2); the original complete
error bounds and minimum half-gap1024 ensure the next midpoint cannot
be skipped. certify.py checks the full error interval endpoints for every
n1..1023. Thus the existing upward rounding remains the correct RNE.
Other branches retain their exact source logic. For n=0 and near/subnormal
callers this shortcut is absent.

The exact source-fragment bare unit covers all1023 exponents, both packers,
widths64..80, signs, parities and binade carries:6132configurations,
12264actual ARM calls and12264 rational RNE endpoint checks. It loads no
firmware or ROM; no SIO access and both states/PCS/SP/bounded writes pass.
The abstract point error intervals use independent polynomial and Q94-ln2
enclosures; this is not a claim that arbitrary synthetic x/h metadata is
a real polynomial evaluation. Only the new upper branch is exercised;
unchanged lower/fallback paths are inherited and covered by public tests.

Fresh60494public inputs/120988fully-profiled states/483952ARM calls pass
MPFR4.2.2, exact parent raw NaN policy, caller SIO/PCS/SP/bounded writes.
All118044frozen parent counts reproduce. Expanded correct-Qfplib deficits
4raw→3raw/6states, one raw fixed and0new. The large-exponent input
5FFA5B2647E9E2C7 now costs READY595/DIRTY655 vsparent2238/2333/Qfplib776.
Seven parent regressions remain:five+3,two+4instructions; none creates a
new correct-reference speed deficit. Public stack640same, bare unit44.

Before adding only static_assert, an8880state short probe executed the
same exact ELF. Its source/logs are preserved as pre-assert evidence and
are not added to qualified calls. static-assert-proof.json verifies both
whole object and ELF identity across the compile-time-only source change.
Fresh public qualification uses the final source hash. Qualified total
496216ARM=483952public+12264bare; inherited/probe calls are not added.

Only two allocated function bodies change, each+8bytes:main raw and
positive normal entry. Total object/linked+16B, no new table/global RAM or
libgcc. All other allocated object/table bytes match, including Q77 near;
generic-M0/M4 allocated compile controls match. Whole public CPP/ASM/ELF
and bare unit rebuild byte-exact. Linked addresses/literals relocate.

Independent review, integration, physical cycles/HW acceptance and the
original full math goal are open. Three main ln inputs, other operations
and general pow totality remain. Historical302/507 producer candidates
and298/507 reviewed candidates do not change. No canonical/Git/device action.
