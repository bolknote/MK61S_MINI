# Private numerator-one reciprocal: author qualification complete

The new hidden mk61_m0_reciprocal1 contract is exact positive numerator1,
R0=0/R1=0x3ff00000; denominator R2:R3 is any binary64. This is not a general
ddiv ABI. The sole root call has verified zero/one loads immediately before
BL and every actual entry is checked. Other resident ddiv callers remain
unchanged. Parent LUT has independent TECH_GO; this new caller requires its
own independent review and inherits no integration/hardware/release GO.

Same120980 pairs/241960states:11377->11372 loss pairs,5 new strict fixes,
0wrong/0newloss/0parentcostincrease.778 states (389 READY,389 DIRTY) save
11-34 instructions. All778 changed paths also have fresh parent calls;
all10254 fresh controls match the full records. All279522 reference-state
variants, including77106 wrong Qfplib outputs/costs, are retained without a
nominal-domain filter. Original153 stays119strict/34slower; author separate
507 stays437, reviewed422. This is not one integrated math executable.

For numerator1, both guarded exponent tests accept exactly1<=E<=2044 and
give R6=2044-E. The guard saves11 accepted /12 E2045,2046 /5 E0,2047
instructions. The exact first product is double(2^31*u1)=(low0,highu1),
saving15 instructions. Eight dead software instructions are removed; READY
retains its nine independent ALU operations before SIO quotient read. Every
actual scalar/public cost matches that formula. After the second product,
R0..R7,R12,SP,NZCV and28 saved bytes match the parent, and all four186B
rounding suffixes are byte-identical.312B exact seed/table unchanged.
Private code1168->1060B (-108B), no new table values, RAM or libgcc. M4/
default M0 controls and six new disabled objects are empty.22 rebuilds exact.

406406 fresh qualified ARM calls:241960 full candidates,778 changed parents,
61524 fresh public MPFR/controls/references and102144 scalar calls.17785
directed MPFR inputs plus110 sNaN policy shortcuts. Superseded product-only
v1 (102144 ARM /12734 MPFR /34sNaN) is separately frozen and excluded. A
missing R6 import stopped the first full/fresh trace preflight after308
completed calls plus two partial aborts and23 oracle evaluations; these are
preserved and excluded. A system-Python recount import failed before any
ARM/MPFR call and was fixed by loading only the pure cost formula. No kernel
fault caused those driver failures. Parent qualification and bare seed
campaigns are inherited, not fresh. Historical producers must not run inside
frozen packets or their superseded snapshots.

Direct1/x denominator coverage includes every exponent/sign, random bits,
4096 normal seed samples and all16 NZCV on IEEE edges. Against numerically
correct Qfplib, parent12560 slow states becomes216 (18 unique denominators),
with24966 faster and no equal. All354 wrong direct Qfplib states remain.
The remaining216 states are explicit in direct-remaining.json:198 with
subnormal denominators and18 normal states lagging2-5 instructions. There
is no universal reciprocal speed claim. Candidate/parent/control direct
stack peaks176B, fresh public controls2148B, full candidate2284B unchanged;
changed-parent subset is not a complete comparison or universal stack bound.

Remaining work includes these scalar deficits, other needed operations,
general pow totality, production source merge/relink and actual R12/loader/
layout guards, the14B old-overlay hazard, physical cycles and release.
No canonical/M4/Git/device/USB/Flash change. Overall goal stays active.
