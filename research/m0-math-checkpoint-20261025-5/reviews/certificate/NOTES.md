Independent private reciprocal certificate review
===============================================

The actual parent is inline0be351d5. Near-one exp is a separately accepted
sibling. The supplier and all historical preflights remain unchanged. The
later parent ROOT7da9 receipt is an additive binding only.

For unsigned16 limbs uh,ul,vh,vl, let S=uh+vh. The complete high product is
uh*vh+C, where C=floor(((uh*vl+ul*vh)*65536+ul*vl)/2^32). Its nonnegative
numerator is at most 65535*S*65536+65535^2. This equals
(S+1)*2^32-(S+2)*65536+1, strictly below (S+1)*2^32 for every S>=0.
Thus 0<=C<=S<=131070. NEGS low/SBCS high subtract one additional unit exactly
when the low word is nonzero. The omitted E is therefore in [0,131071].

Writing A=(B-uh*vh) modulo2^32, the original sign argument is H=A-E modulo2^32.
The certificate accepts only when (A&0x7fffffff)>=131072. On the positive
interval H>=1; on the negative interval H>=INT32_MIN+1 and remains negative.
Both signed discontinuity bands, including all H=0 and H=INT32_MIN cases,
use the complete original multiplication/borrow/CMP path. A+d restores B
even when the earlier subtraction wrapped. Incoming NZCV is irrelevant.

The emitted 12-byte nonbranch prefix is identical in the unit and both real
production paths. The two decoded branches target the exact full/down
entries. The original 42-byte complete product/NEGS/SBCS/CMP sequence is
byte-identical after restoration, as is the 30-byte round-and-pack suffix.
The pre-certificate arithmetic has only the intended removed zero shift and
branches to relocated packing labels. The independent comparison normalizes
only those decoded target addresses.

The certificate supplies a sign, never a replacement product value. At the
up target ADDS resets carry before ADCS. At the down target the quotient
shifts consume no old NZCV. R2 is freshly defined before use, R3 and the
omitted product limbs are dead, and saved R4-R7 are restored before returning.
The live quotient R0/R1, sign/exponent R12, own-entry SP and frames match the
original at every checked downstream join. The extra shift removal requires
the actual positive-one caller: raw R0 is zero through the first two products,
R4=R0<<5 is zero, and both normalization paths preserve it. No generic ddiv
contract is inferred.

Own CPU qualification consists of 3904 bare Thumb calls (1952 cases, all16
flags), 1472 scalar calls (184 flag jobs/49 denominators), and216 calls from18
public pow pairs against all three real Qfplib compositions, for5592 total.
There are61 actual directed MPFR evaluations and6 explicit sNaN shortcuts.
All8 combinations of fast/full, up/down and cross-carry are covered in actual
private execution. There are324 pre-certificate and zero-yL joins,134 complete
fallback restorations,332 after-second-product joins,164 real inline contexts
and READY9ALU checks,8 nested pow contexts,384 original-frame entry/POP checks
and16 actual root return-site checks. Inline SP is its own entry SP minus20,
not the outer Machine SP. No numerical preflight failed or was discarded.

The complete saved public and scalar corpora were recounted without rerunning
them. Parent cost fields were checked against the immediate parent's raw
candidate cost. Public losses11371->11369 comprise one strict pair fix and one
equality pair fix. 354 states become faster and32 become slower (+7/+8).
Of those32, two already lose to every correct Qfplib composition and become
slower still: READY1697->1705 and DIRTY1706->1714, against1526/1547/1584.
The additive corrigendum is bound to all frozen/raw pins and reproduced on
actual Thumb. The other30 have no correct Qfplib reference. Zero new loss-set
members is not zero performance regression.

The same expanded scalar corpus has1132 parent increases, all retained.
Correct-Qfplib comparisons become32382faster/5equal/1slower. The remaining
DIRTY denominator3FF27D0DF6735E90 is149 instructions versus146. Own bounded
execution retains64 cases each of+7 and+8. No universal parent or Qfplib speed
claim, adoption decision, physical cycle claim or general pow totality follows.

Four reviewer HOST-only failures are retained: an incomplete marker stripper,
linker STT_FILE basename mismatch, Python assertion syntax, and comparison of
PC-relative branches to relocated packing entries. They executed zero ARM and
MPFR calls. The ten already successful rebuilds were reused, and only unit
ELFs were relinked after preserving the failed whole-file comparison. Twelve
qualified own rebuild outputs are byte-exact. The unit r2 changes only its R1
preservation assertion; source and binary equality with its predecessor is
checked. Wrapper timings and stack are not production performance evidence.

Allocation is1108B versus1072B (+36), with unchanged256B table and no added
writable RAM or libgcc. The author full-corpus stack2284, public controls2148
and scalar176 are separate observed corpora, not a universal stack bound.
Own scalar stack is176 and bounded public968, equal across parent/control/new.
Reviewed507 remains422; author438 does not change that accepted result.

Source merge/relink with near-one, fresh actual integrated shared-R12 and
loader/layout guards, the old168B overlay's14-byte table-entry overlap, broad
math qualification, physical timing, hardware, main and release remain open.
The next known-zero study is outside this finite review. No device, network,
Git, canonical state, product source or Flash was accessed or changed.
