# Reviewed scope

Exact child4db4753b / ELF2c0d376f of accepted ln2-sign661ae2b6 /
9f872b40. This private component verdict covers coefficient remainder,
denominator-band, exponent and cheap-k0 gates with exact metadata passing.
Argument helper, numerical polynomial, tables, Q77 near, fallback,
generic M0 and excluded M4 paths are inherited. No whole-ln/507,
canonical, integration or hardware verdict follows.

# Source-derived one-sided operations

Write S=2^70, u=computed_integer_argument/S and H=true_argument.
For a denominator band d, both are below hmax=1/(d-1), because
H<=1/den<=1/d and |u-H|<=A/S with A=106497/16384. The tighter actual
seed bound1/d+A/S also proves integer argument<2^59 and square<2^48.
The coarser closed hmax alone must not be used to prove those strict
machine-domain limits; the first own checker draft stopped on exactly
that distinction before ARM execution, and its log is retained.

With t=floor(argument/2^27), l=argument mod2^27, the actual square is
floor(t*t/2^16)+floor(t*l/2^42)+1. The true scaled square is the same
unfloored first two terms plus l*l/S. Therefore square error lies in
(-1-2^-16,1]. The accepted cube product error plus u times this square
error gives C=35/64+hmax*(1+2^-16). All cube/helper domains are preserved.

The fourth power is floor(floor(cube/64)*t/2^37). Truncating cube/64
loses at most63/64, multiplied by t/2^37<64*hmax: its contribution is
63*hmax, not63*64*hmax. Truncating t introduces less2^-43 times the
nonnegative cube. Including final floor and cube error gives
e4 in(-F4minus,F4plus) with
F4minus=1+63*hmax+(S*hmax^3+C)/2^43+hmax*C,
F4plus=hmax*C. Applying the same argument to floor(fourth*t/2^43)
gives e5 in(-1-hmax*F4minus-(S*hmax^4+F4plus)/2^43,hmax*F4plus).
No cross product, truncation or final floor is dropped.

The unchanged nearest-third helper is exact integer nearest /3, so its
coefficient rounding error is at most1/3. Its32-bit reciprocal quotients
are exact; rh+rl carries0or1 and the final remainder2 rounds upward.
The fourth and fifth coefficient errors are retained explicitly:
r4=fourth-4*floor((fourth+2)/4) in[-2,1],
r5=fifth-5*floor((fifth+2)/5) in[-2,2]. For every fifth<65536,
52429=(2^18+1)/5 and the extra reciprocal fraction cannot reach the
next integer. The multiply-shift is therefore exactly floor((fifth+2)/5),
with its full product below2^32. This is an all-domain algebraic proof,
not an inference from re-running the author's65536 samples.

The known coefficient bias is r4/4-r5/5 for positive offsets and
r4/4+r5/5 for negative offsets. Its range before output-sign reversal
is[-9/10,13/20]. Square ceil rounding contributes[-1,(1+2^-16)/2].
Add center error±1/2, cube/third error, fourth/fifth errors, nonlinear
argument error±A*hmax/(1-hmax), and the positive fifth-degree Taylor
omission. The interval sums in bounds.py independently produce all three
bands; every emitted L/U constant is strictly larger than its actual
rational bound. Negative logarithm magnitude negates the coefficient
bias and swaps L/U.

# Residual, exponent, integer gate

The exact signed residual r=delta*2^29-h_integer*den is recovered from
its modulo-2^32 low word since |r|<32768. With v negative iff offset
and result signs differ, linear magnitude error is -v*r/den. The accepted
Q70 ln2 error lies strictly in(-1/2,0); magnitude contribution is(-n/2,0)
for either exponent sign. Recovering n from2*ceil(n/2) minus original
exponent parity is exact for all2046 normal exponents. n0 cannot
underflow because its actual exponent1023 has the required zero bit.

The magnitude error lies strictly inside
(-L+bias-oriented/den-n/2, U+bias-oriented/den).
The factor40 integer predicate is exactly the test that the upper
endpoint is<=distance above a midpoint, or the lower endpoint>=-distance
below it. The actual rational bounds are strictly inside emitted L/U,
so integer equality is safe. Actual callers decline distance0 before
using this helper. Signed expression magnitude is bounded by172096450,
below2^28. All int32 products, negations and conversions remain safe.

The global error is below1024 Q70 units. Width64 implies n<=1 and
error below512, preserving the narrower lower-binade half-cell. Other
widths retain the previous larger gaps. Unchanged guard distances and
retained-bit carry ensure no adjacent midpoint or binade is skipped.

# Cheap gates and the endpoint nuance

Restoring coefficient extrema gives raw lower radii3negative/4positive
and upper6. For exact floor(H)+1, the argument's log error is one-sided;
removing the raw symmetric nonlinear allowance gives lower4 and upper
6negative/7positive. These source predicates depend only on admitted
main k0 calls. Near radius4 is excluded from the coefficient extension.

The first32 cells have den<=2111. Offset high>=1022 implies positive
offset H>=255/(256*2111). The positive P5 omission is at least
S*u_min^6/(6*(1+hmax)). For exact argument, u_min=Hmin. For raw argument,
u may lie BELOW H: this independent proof conservatively uses
u_min=Hmin-A/S. The producer's displayed Hmin-only lower estimate needs
this small refinement for raw. The correction changes the omission by
about1.51973e-16 Q70 and leaves lower bounds0.948391118raw and
0.945215710exact, both strictly below radius1. Thus no source change or
additional hardware gate is required; this additive proof closes the
premise without editing the frozen producer document.

# Binding, execution, costs

Removing only the new helper/packer replacements and reversing metadata
forwarding reconstructs the ENTIRE parent source exactly. The literal
bare helper and both packer fragments match production. Complete private
CPP and ASM objects, whole ELF and bare unit independently rebuild
byte-exactly. Only raw1368→1744 and normal1272→1784 object bodies change:
+888B; other allocated sections, BSS, tables, Q77 near and ASM are equal.
All39 actual resident bindings match. Generic M0 controls are exact;
M4 controls are excluded zero-allocated TUs, not platform qualification.
Linked addresses/literals may relocate; old absolute linked identity
is not claimed.

Own1396 ARM calls comprise426 public calls (71raw×two SIO×three images)
with fresh MPFR4.2.2,650 bare coefficient calls and320 bare pack calls.
All nine fixed and five remaining raw deficits are replayed. Every one
of19 retained regression-cost classes, including+108, has a real public
witness. Bare tests include all coefficient remainder combinations,
denominator edges2049/2079/2081/3583/3585/4095, output/offset signs,
equality, n parity, midpoint decline, k0/endpoint boundaries and54 forced
new-coefficient pack points.188 exact Fraction RNE interval endpoints
agree. Bare fixtures are abstract interval/transport tests, not extra
real-polynomial public inputs. PCS/SP, bounded writes, full DIRTY SIO,
READY dirty-bit state and fixture preservation are checked; bare SIO
accesses are zero and bare PC stays in its standalone unit.

Saved177178 state rows are recounted, not reexecuted:120988 parent
counts retained; expanded14 raw deficits→5,9 fixed,0 new. All seven
earlier endpoint-probe parent losses close. Seven additional old control
deficits are retained separately, two close and five remain. All85604
parent regressions remain, not hidden behind correct-Qfplib eligibility.
Most cost1..7 extra instructions; maximum is108 on a preexisting fallback.
Own public subset stack520candidate/496parent is reported separately
from author wider maxima648/640; +8 is the difference of those maxima,
not a promise that every individual input changes stack by8. Bare stack72.
No physical timing, normal builds, devices, Git, leases or promotion.
Reviewed original coverage remains298/507.
