# Exact log quotient endpoint predicate

Private RP2040 child of the frozen near-ln directional component. Only
one endpoint condition changes to an equivalent high/low-word predicate.
All arithmetic/rounding/table/primitive algorithms remain unchanged.

Fresh33086 unique inputs/66172 fully profiled state cases,264688 public
ARM calls, zero own errors against fresh MPFR4.2.2. All65880 parent
instruction counts reproduce. PCS/SP/bounded writes/caller SIO/raw parent
NaN policy pass. Bare helpers add229300 calls for57325pairs across all1024
denominators, both SIO states, exact integer floor and no SIO accesses.
That test loads only the component plus its existing184-byte source-bound
product capsule; no firmware/ROM. Qualification total493988 ARM calls.

Five old DIRTY losses722->718 now beat correct Qfplib719. ln2 DIRTY
613->610 versusQfplib711; READY599 is unchanged. On the same old corpus
51raw losses become46. New low-word-wrap controls expose27 preexisting
losses, so the enlarged corpus has parent78raw versus child73raw/118state
losses. Zero newly introduced correct-Qfplib deficits. All controls,
incorrect reference answers, losses and regressions remain in reports.
Historical ln remains6/10 fixed,4open; no whole-ln or whole-math GO.

All33086READY counts are identical. DIRTY10197faster/22863equal/26slower;
each regression is one instruction. The extra controls include these
regressions and do not hide their still-correct answers. Allocated code/
data size0, stack640 unchanged on this same corpus, helper stack68.
Only232-byte helper body changes within shared3800B section; every other
function/literal/padding byte, all other sections/tables/deps and the ASM
object match. GenericM0/M4 controls match (not a whole-M4 image build).
Entire public CPP/ASM/ELF independently rebuilds byte-exactly. Linked
near body/table keep exact addresses/bytes, inheriting the parent's
16896 bare packer calls without counting them as fresh. No new mathROM.

Source:79067df1532a771c3cef484271292d7a592f73e1a0e0d51af86b5359c3de33a7
ELF:5187e1bbba29ec6b0d24cfc57aba9feb74598cc0b8df0df06fe6b13a53039e7e
Object:dc71644b976e5c6108412aa2ee371c6e0c8a2621f94bcdea94d0dceadeb17bbc

Hold this packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. Other needed
operations, general pow totality and the original full goal remain OPEN.
