# Main ln without exact software quotient correction

Private RP2040-only child of the independently accepted small-low-limb
quotient component. This does not change its exact helper API or any
pow/subnormal/near/generic-M0/M4 path.

The positive-normal public entry first handles its existing special and
near-one domains. Outside them, the low-word predicate is symmetric under
negation: delta_low = +/-input_low modulo 2^32, so input_low in[-64,64]
is exactly the accepted quotient family. Only inputs outside this family
and with SIO CSR DIRTY set branch to a separate raw normal body. The
ordinary exact body is source-identical after removing that dispatch.
The raw body retains every original polynomial, table, magnitude, ln2
and rounding operation except its initial h and final certified pack.

For odd den=2049+2*index, H=delta*2^29/den. Existing reciprocal rows are
R=floor(2^75/den)&~63 and the existing product46 gives |h-H|<106497/16384.
The original rational polynomial propagation gives the generic complete
bound13.400120688467078<16 Q70 units. Subtracting only the linear argument
term leaves B=6.900059653310828<7. The nonlinear amplification term is
retained in B. For the actual captured h, r=(delta<<29)-h*den is recovered
exactly as a signed low32 value, |r|<2^15. The approximate magnitude error
is -v*r/den +/- (B+ceil(abs(k)/2)), where v is negative iff the offset sign
and output ln sign differ.

At midpoint distance d>=16+extra, the generic bound suffices. Otherwise
an exact midpoint declines. Above a midpoint the cold sufficient condition
is den*(d-(7+extra))+v*r>=0; below it the final term is negated. Because
B<7, equality is safe. An uncertain interval uses the unchanged ln_refine
on the original x. No guard weakens the rounding requirement.

Outside near-one, |ln(x)|>1/128 and <1024. Pack shifts are11..27 and the
ordinary smallest midpoint half-gap is1024. At a power-of-two output the
lower half-gap is halved: width64 requires k in{-1,0}, extra<=1, bound17
below512; widths>=65 have lower half-gap>=1024 above the maximum bound528.
The signed cold expression is below2^22; all unsigned low-word operations
are defined modulo2^32. The final retained rounding handles binade carries.

certify.py verifies the source transformations, all1024 actual ELF
reciprocal rows, rational bounds and860160 discrete interval tests. The
exact inline pack is compiled without firmware or ROM and executed32338
times in both SIO states. Its16169 configurations include all1024den,
both magnitude orientations, signed residuals, midpoint distances, output
binade boundaries/carries and widths64..80. All22364 rational accepted
interval endpoints yield the same binary64 RNE. No SIO access, input write,
PCS/SP or bounded-stack failure occurred; unit stack56B.

Public qualification retains and recounts all68876 parent state cases and
adds all1024den across extreme/ordinary exponents plus family/guard controls.
Fresh MPFR4.2.2, exact parent NaN policy, both SIO states and PCS/SP/bounded
writes are checked on every call. Results and costs are separately recorded
for pinned resident, Qfplib, parent and candidate, including wrong Qfplib
outputs and every parent regression. This is instruction profiling, not
physical cycles or a whole-input speed/correctness proof of the fallback.

Object isolation shows only public main ln dispatch and new raw body change:
28B plus1356B, no tables, RAM or dependency additions. The whole private
CPP/ASM/ELF rebuild is byte-exact. Generic-M0 and M4 compile controls retain
allocated code/data identity; this is not a whole-M4 firmware build. Other
object bodies and table data match, while linked addresses/literals relocate.

Whole-library integration, independent review of this new delta, physical
measurements, the remaining ln cases, general pow totality and the other
operations in the original user goal remain open.
