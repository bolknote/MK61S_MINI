# Independent exp-tiny component proof and acceptance limits

This review concerns the RP-only change for 2^-54<abs(x)<2^-38 in the
sealed full native CPP source. It accepts exact returned-bit rounding for
that domain, source/ABI closure, and the stated ISA path results. It does
not accept general-exp totality, an integrated math firmware, hardware
cycles, publication, IEEE exception flags or the complete math goal.

## Independent rounding derivation

Write |x|=M*u, u=2^(e-52), 2^52<=M<2^53 and -54<=e<=-39.
The output lattice spacing is h=2^-52 for positive x and h=2^-53 for
negative x. For sign bit n, put s=-e-n. The linear displacement in output
units is M/2^s. A linear midpoint has M0=z*2^(s-1), where z=2*r+1 is odd
and r is the retained quotient. All results remain close enough to one
that neither lattice changes spacing in this domain.

Define C=(exp(x)-1-x)/u. Convexity gives C>0 for x!=0. Bounding the
absolute exponential series by a geometric series gives
C<M^2*u/(2*(1-2^-38))<2^14/(1-2^-38)<16385.
Thus only distances d=1..16384 from a linear midpoint can need correction.
At an exact linear midpoint, C>0 decides the direction directly; there
is no mathematical RNE tie of exp at that input. At every other unguarded
midpoint distance, the integral distance is at least 16385, so it cannot
be crossed. A correction cannot reach a second midpoint either, because
2^s is vastly larger than this bound.

At M0 the quadratic correction in input-ulp units is
C0=M0^2*u/2=z^2/2^q, q=55-e-2*s=e+55+2*n.
Throughout the complete range, 1<=q<=18 and z<=65535. Therefore z*z is
an exact uint32 product. Since z*z is odd, its fractional distance from
an integer is at least 2^-q>=2^-18. Independently enumerating the complete
midpoint set finds the stronger actual minimum 1/65536; the author's
weaker 2^-18 separation is safe.

For |M-M0|<=G=16384, the quadratic displacement error is bounded by
G*(2*2^53+G)*2^-92. The cubic and higher error in input-ulp units is
below 2^-23/(6*(1-2^-38)). Their combined exact rational bound is
1208925819612155273543677/15211807202683412585739309809664,
strictly below 2^-22. Thus the actual C cannot cross either integer next
to C0: floor(C)=floor(C0), and C can never equal the integral distance d.
For positive x, the upper result is selected exactly when d<=floor(C0).
For negative x, subtracting the positive correction from the magnitude of
linear displacement selects its larger magnitude exactly when d>floor(C0).
These are the two different comparisons in the source and actual ASM.

The high/low word implementation is exact. Since 38<=s<=54, the quotient
M>>s is high_word>>(s-32), with shift 6..22. A positive guarded point is
exactly tail+1==half and lo>=2^32-16384; its distance is 2^32-lo. The
unsigned source comparison lo>0U-16385 recognizes precisely that set.
A negative guarded point is tail==half and 1<=lo<=16384; its distance is
lo. Exact half lo0 is handled by the default direction. Every shift and
the odd construction are within uint32 bounds. Returning the raw one
constant plus/minus the rounded displacement packs the correct binary64.

The independent enumeration uses odd midpoint endpoints directly rather
than the author's model loop. It derives 16385 positive and 32768 negative
cells, total 49153. All denominator shifts, integer separation and product
bounds are checked for every cell. The author 442299 model controls are
inherited evidence and are not counted as own checks.

As a second independent oracle, 934 selected controls use a rational cubic
P=1+x+x^2/2+x^3/6 with interval remainder t^4/(24*(1-t)), t=abs(x).
Rounding both exact rational endpoints onto the relevant binary64 lattice
must give the same answer. This does not use the floor(C0) decision or the
author's MPFR oracle. The controls target every exponent/sign, minimum
separation cells, floor transitions, old/new guard 4096/4097 and 16384/16385,
word carries, domain endpoints and independent raw values.

## Actual paths and ISA costs

The helper has eight possible instruction paths. Their costs are 40, 43, 45,
46, 49, 50 or 59 instructions; positive and negative guarded paths both cost 59.
The public tiny prefix/suffix adds 34 instructions, with three additional
instructions when the magnitude high word equals 0x3c900000 and lo!=0.
Accounting for valid combinations gives exactly 11 full public tiny paths
and costs 74, 77, 79, 80, 83, 84, 87, 93, 96. Own actual ARM executions cover all
paths and every predicted cost, through both the public entry and a helper
compiled separately from the exact source body.

Pinned qfp_dexp unconditionally executes its loop with r7=1..32 after
normal tiny unpack/reduce returns. Only the loop-end ADD changes r7.
The shorter branch has 11 instructions per iteration, so that loop alone
costs at least 352 instructions. Consequently every new tiny path is faster
in ISA count, irrespective of whether Qfplib's numeric result is correct.
Own traces verify all 32 iterations for every tiny Qfplib call; the observed
minimum in the own corpus is 466. Physical cycles are not inferred from
these instruction counts.

The new outlined layout avoids an unrelated register-allocation regression.
Own bounded execution of40861E1EFFBB4B16 confirms parent 556, rejected inline
trial 561, final outlined 556, Qfplib 559. Returned bits agree. The two own
trial calls are excluded from accepted-candidate qualification counts;
the rejected trial is never treated as a parent.

## Exact source, load and stack binding

All 80 frozen artifacts, 513 lineage pins, and the accepted f2d receipt plus
its 27 references (28 pins including receipt) were reverified. The control
CPP object exactly matches accepted rsqrt CPP; full ASM exactly matches
accepted f2d/d2f ASM. This is composite component lineage, not one integrated
repaired-platform image. Only `.m0_exp_core`5144→5012 and new
`.m0_exp_tiny`196 change, net+64 selected CPP bytes. All other CPP allocated
bytes and semantic relocations are identical. Complete RP ASM, including
d2f256 and f2d172, is identical. Generic M0 selected CPP is identical; M4
selected CPP is empty and identical. Generic/M4 ASM evidence is inherited
from the accepted byte-identical sources; no whole M4 firmware is claimed.

Twelve own-output rebuilds reproduce the selected complete CPP/ASM objects
and both exp ELFs byte for byte, including debug/stack-usage outputs.
The exact helper text is also compiled separately with the RP flags. A
discarded retention anchor keeps it emitted; no anchor is executed. All 196
helper bytes match the full source object and tested linked ELF. The bare
unit contains only that actual helper, with no relocations, external calls,
ROM, firmware or mock. It is not the 16-byte Flash product wrapper.

Public mk61_m0_exp and compact_math::exp are aliases of the same 1276-byte
entry body, with no added interposition veneer. Its section is 5012 bytes;
the section size must not be confused with that function size. Dependency
bindings equal accepted/resident addresses. The unchanged product wrapper
is resident code bound at its existing address; the exp overlay loads only
the accepted 168-byte RAM product plus CPP Flash. Explicit two PT_LOAD
segments cover Flash 0x101a0000..+16008 and RAM 0x20038ee4..+168, without ELF
headers/padding writes to neighboring resident addresses.

Static core stack increases 88→96 bytes and helper stack is 20. Every tiny
public trace stays within core/helper and at most 116 stack bytes; bare
helper uses exactly 20, five in-section literals and no SIO/global data.
DIRTY state preserves all 28 bytes; READY is left not DIRTY. In own 972
inputs, observed full candidate peak is 376 versus 736 in both accepted and
rebuilt parent controls. The author also observes 376 versus 736 over the
same old 48763 corpus. These are bounded corpus maxima, not a universal
stack theorem for the full exp implementation.

## Evidence and remaining work

Own qualification comprises 7776 public ARM calls across four machines and
two states, plus 1822 bare helper calls: 9598 qualified calls. Own972 oracle
evaluations comprise 970 actual directed MPFR inputs and two pre-MPFR sNaN
shortcuts. The 934 rational interval controls are separate mathematical
checks. Two rejected-layout calls are additional, explicitly excluded.
All original 16 exp inputs and both remaining hard cases are checked freshly.

The author-qualified totals reconcile as 327350 candidate calls plus 229824
new Qfplib calls plus 960 fresh parent-audit calls = 558134. There are 163675
oracle evaluations, 163673 actual directed MPFR inputs and two sNaN shortcuts.
The 97526 old input/state rows contain inherited parent and Qfplib measures,
not fresh calls. Seventy new remaining-state parent costs come from the
excluded final smoke probe;960 remaining-state costs were separately
acquired. The 10446 smoke calls and rejected inline trial are excluded.

All 327350 raw records were streamed and reconciled, without broad ARM
re-execution. Old 48763 raw outputs agree with the accepted parent on every
state. There are 98303 valid integer transition-neighbor locations from
the 49153 cells in the actual fresh acquisition. Three formal locations
fall outside that binade/helper domain; their adjacent-binade and caller
endpoints are separately acquired. Thus the universal cell proof is tied
to real input records rather than only to generated model files.

On the same old 48763 inputs, losses 395→154, with 241 fixes. The expanded
163675 corpus has 669 losses:154 old, 514 added dense controls at/above
2^-38, and one added ordinary C08357D5691B8C00. Every 669 loss was already a
parent loss. Different-size corpus counts must not be subtracted. All
115028 wrong-Qfplib state rows remain. Known 13234 parent cost increases
(+1..19, sparse values) remain recorded and still cost less than Qfplib.

Original exp hard cases 4085F424184F6DC5 and C041265824E2113C remain 2268/649
and 2248/622 instructions respectively. Original507 stays 418 accepted
separate component cases, with 89 remaining. Expanded 669, ln 5, FMA,
generalpow totality, complete combined regression, platform integration,
hardware/physical cycles, canonical promotion and release remain open.
Whole firmware size and possible GC effects are not claimed.

Reproduce with binding.py, proof.py, evidence.py and arm.py using the
configured Python venv. Only this independent directory is written.
Unicorn JIT requires host execution outside the restricted sandbox. No
script accesses USB, devices, Flash, leases, Git, canonical sources or EA9.
