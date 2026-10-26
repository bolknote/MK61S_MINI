# Private exact reciprocal remainder certificate: author qualification complete

Parent is inline0be351d5, itself pending separate review. Existing soft/LUT/one
reviews and ROOT receipts are pinned without extending their acceptance.
Contract is exact positive numerator1, denominator any binary64; not general
ddiv or a one-argument C ABI. The sole actual root caller remains unchanged.

The certificate omits a bounded part of one high product: its correction is
always between0 and131071. Its integer interval check excludes both signed
discontinuities. A decisive sign uses the cheap path; otherwise the original
complete product, borrow and sign check run. Zero retains the parent tie
behavior. NUMERIC-PROOF.md supplies the whole uint32 proof. The same exact
macro is used in production and100800 bare test cases /201600 ARM calls,
including all16 NZCV at both boundaries. R1/R12/PCS/SP/PC and only wrapper
stack writes are checked. Private numerator+1 additionally proves yL=0 and
removes one dead shift. All actual before-certificate and after-second-product
R0-R7/R12/SP/NZCV/frame28 joins match. Every certificate branch is audited.

Same120980 pairs /241960 public states:11371->11369 raw loss pairs, one strict
fix and one equality fix; no new loss or wrong result.354 states save12-15
instructions.32 states add7-8; all remain no slower than their correct Qfplib
references. All778 reciprocal paths have fresh parent replays, including
unchanged controls. The complete corpus retains279522 reference-state
variants, including77106 incorrect Qfplib variants and costs, without domain
filtering. All10254 fresh public controls match the full saved records.

Same expanded scalar corpus:20994 input/flag cases /41988 SIO states,
correct-Qfplib losses13->1,32382faster/5equal/1slower. The remaining state is
DIRTY denominator3FF27D0DF6735E90:149instructions vsQfplib146. All9600 wrong
reference variants are retained.1132 scalar states add7-8 parent instructions,
with zero new Qfplib losses. This is not universal reciprocal speed parity.

673814 fresh qualified ARM calls:241960full candidates+778parent paths+
61524fresh public controls/references+167952scalar+201600bare unit.
26011 directed MPFR inputs plus110 separately reported sNaN policy shortcuts.
Two host-only preflights are preserved/excluded: incorrect section selector
before compilation, and exact NaN payload comparison in the first recount.
Neither executed ARM/MPFR; all numerical campaigns completed once. Parent
campaigns and the old integer model are inherited, not fresh.22 own source,
object and ELF rebuild outputs are byte-exact.

Private code1072->1108B (+36B), no new tables/RAM/libgcc; the same256B table,
inline seed and READY9ALU gap remain. Six added disabled objects are empty;
selected defaultM0/M4 and all other resident sections are unchanged. Full
observed stack2284B, fresh public controls2148B each, scalar176B each, unchanged.
The parent path subset is not a full stack comparator. Original153pow now
120strict/33slower. Author separate507union438=432strict+6equal; reviewed422
unchanged. These are separate components, not one integrated executable.

Next work: preserve the known zero through the second product and reuse it
for rounding, seeking the last three scalar instructions; then source merge
and relink with near-one exp, actual integrated R12/loader/layout guards and
the14B old-overlay hazard. Other math, general pow totality, physical cycles
and release remain open. No canonical/M4/Git/device/USB/Flash mutation or
integration/hardware/main/release GO. Frozen producers must not be rerun.
