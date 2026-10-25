# Independent PRIVATE numerator-one reciprocal component

Supplier3341f37f has actual parent LUT7384323f / independentc1911a7d.
LUT ROOT19a0b7fc is later additive evidence; the child retains only the soft
ROOT receipt present at its seal. Its frozen result and files are unchanged.
All80 local and2142 external pins and ten own full object/ELF rebuilds pass.

The new hidden entry is mk61_m0_reciprocal1. Its register contract still
places positive binary64one in R0:R1 and the denominator in R2:R3. It is not
a one-argument C ABI or a replacement for every ddiv caller. The sole root
BL has the verified MOVS R7,0 / LDR R1,3FF00000 / MOV R0,R7 sequence, with
no intervening symbol, entry label or direct branch target. Its instruction
address and return address are unchanged. All other ddiv callers stay bound
to the old function. The later software entry remains private and requires
the exact guarded R6, raw operands and original20-byte frame.

The guard proof covers all2048 denominator exponent values, independently
of sign/fraction. Both old and new predicates accept exactly E=1..2044 and
give R6=2044-E. The instruction savings are11 accepted,12 for2045/2046 and
5 for0/2047. Rejected IEEE inputs preserve all raw operands and the old
fallback. Zero, infinity, NaN, subnormal and extreme normal denominators are
covered in the bounded CPU checks, including all remaining loss inputs.

For every uint32 u1, P=2^31*u1 has low=(u1&1)<<31 and high=u1>>1.
Doubling gives low0 and high=2*(u1>>1)+(u1&1)=u1, including carry. The old
long-product cross carry is always zero, so it executes17 instructions;
MOV R5,R6 and MOVS R4,0 execute two. The saving is exactly15. Following it,
LDR overwrites R2; the second macro overwrites R1/R4/R7/R3 before reading
their old values and establishes flags before BCC. Thus dead temporaries
and incoming flags cannot affect its result. After this second product,
R0-R7/R12/SP/NZCV and28 saved bytes agree; the four186-byte RNE suffixes are
byte-identical. This is an exact identity, not reduced precision.

Only software removes six numerator-unpack instructions and two R0 seed
setup instructions. The removed R1/R4 values die before their next read;
the unchanged312-byte LUT seed overwrites R0 from D at its first instruction.
Its new R3 clobber is still protected by the actual saved-R0-R3 caller.
Hardware preserves the complete nine independent ALU instructions between
SIO divisor issue and quotient read, verified both statically and dynamically.

Own CPU-only Unicorn qualification is3588 Thumb calls:3384 scalar calls on
423 flag-jobs/48 distinct denominators and204 public calls on17 pairs.
There are61 actual directed MPFR invocations and4 sNaN policy shortcuts.
Scalar expected results are cached per denominator and reused across NZCV
patterns; they are not counted repeatedly as fresh MPFR calls. All nine
normal remaining-loss denominators run at all16 NZCV values in both SIO
states, and all18 remaining unique denominators plus IEEE/dyadic/guard edges
are included. Every public entry proves numeratorone and the single root
return address. All scalar/public return POPs restore the original frame;
the public return sites are observed again after return.

All318 after-second-product state/frame comparisons pass, as do157 fresh
R3 save/pop/private-frame checks. The original20-byte frame, R6, R12, seed
8-alignment and all7 DIRTY SIO words are preserved. The READY issue/read
contract remains nine ALUs. Every own/public/scalar cost equals guard saving
+15 per first product +8 per software seed. All five new strict public fixes
were independently executed against all numerically correct real Qfplib
references. Wrong Qfplib outputs and costs stay in the evidence.

The complete saved corpus was recounted against the immediate LUT parent:
120980 pairs/241960 states/279522 reference variants, including77106 wrong
variants. Loss pairs11377 to11372, five strict fixes,778 faster states
(389 READY,389 DIRTY),11-34 instructions saved, no new losses/wrong results/
increases. All10254 fresh controls match. The overwritten immediate-parent
cost field is parent_reciprocal_instructions; old historical costs are not
substituted. Original153 remains119 strict/34 slower, reviewed507 stays422.

All25536 saved scalar rows were recounted. Parent12560 slow states become
candidate216 slow /24966 faster, with354 wrong reference states retained.
The216 deficits cover18 unique denominators:198 subnormal states and18
normal states at nine denominators. The author's additive corrigendumcf6766bf
is byte-bound and independently confirmed: normal READY lag2-5, DIRTY15-21,
overall2-21 instructions. Its167 versus146 DIRTY witness was reproduced.
The old HANDOFF2-5 figure described READY only. No universal1/x speed claim
is made, and these remaining deficits remain work.

Author406406 qualified calls are separate from own3588. Superseded v1
102144 ARM/12734 MPFR/34 shortcuts, failed trace308 complete plus2 partial
calls/23 oracle evaluations and static-import0 remain preserved and excluded.
The reviewer also preserves two HOST-only preflights (draft syntax and exact
disassembly spelling), both0 ARM/MPFR. No own ARM call failed or was discarded.

The private section shrinks1168 to1060 bytes (-108), without new table values,
RAM or libgcc. The current free-Flash layout is below2MiB. Complete saved
stack peak2284 and author controls2148 remain unchanged; parent changed388
is a subset, not a whole-corpus comparator. Own direct176 and selected public
968 peaks match in all three images. Physical cycles and universal stack
improvement are not claimed. Near-one remains a sibling. Source merge/relink,
actual integrated shared R12 and loader/layout checks, the old168-byte exp
overlay's14-byte table hazard, general pow totality, remaining math and
hardware/release remain separate. No device/network/Git/canonical edits occur.
