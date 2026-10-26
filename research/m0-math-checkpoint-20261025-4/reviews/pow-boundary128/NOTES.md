# Boundary128 independent component review

This is a PRIVATE component result. The actual parent is Square128 r2
(`31de9242…`), whose accepted review is `eaa55a85…`. Near-one is a separate
sibling. The new caller required its own review and receives no main, merged
firmware, hardware, cycle or release qualification from these checks.

The candidate changes exactly the old boundary section. The resident 532-byte
slot holds `LDR R3,literal; BX R3`, an aligned Thumb target and 524 bytes of
padding. The new 228-byte section comprises 212 bytes of code and 16 bytes of
literals. Its three calls resolve to the actual accepted 232-byte square,
the original 490-byte multiply, and the original 372-byte compare. The helper
remains 94 bytes. The multiply allocation includes two GAS alignment bytes;
the independent ARM PC guard excludes those bytes and every literal pool.

For a normal cell c let M=(c&fraction)|2^52 and C=2M+1. Both initializers form
H=C<<10, L=0, exponent=biasedExponent-1023, radius=0. The shifted word fields
do not overlap, so OR and the old ADD give the same two high words. The old
carry guard admits high word 00100000..7FEFFFFF when low!=FFFFFFFF, and
00100000..7FEFFFFE otherwise. This is exactly the new unsigned cell interval.
Both loops execute floor(log2(denominator)) squares. The old inline square
implements the accepted Square128 transform on all 24 bytes, including its
modular carry, normalization and +16 radius rule. Induction therefore gives
identical midpoint objects; using the accepted square changes scheduling,
not precision.

The noninverse path passes the same original power and midpoint to the same
compare. The inverse path passes the same operands to the same multiply and
retains the signed exponent tests and the high64/low64/radius comparisons
against one, including the modular -radius threshold when radius is zero.
Side zero still means undecided. Existing public enclosures, fallback and RNE
packing are unchanged. This is preservation, not a proof of general pow
totality.

The pointer, denominator and bool occupy R0-R2. ABI alignment puts the fourth
uint64 argument at incoming SP[0:8], leaving R3 unused. The tail preserves
R0-R2, LR, SP and that cell; the C++ body returns an ordinary int32 in R0.
Fresh disassembly binds all four retained calls in pow_root128_decide and
the three new BL destinations. There is no additional boundary R12 return
contract. The shared product's separate R12 contract still needs its guards
in the actual future merged ELF.

Five own full object/ELF rebuilds are byte exact. Every one of the 68 local
and 1695 external pins was checked. The complete saved 120980-pair / 241960-
state corpus was recounted against the accepted parent stream, including all
279522 reference variants and 77106 wrong Qfplib outputs. Current parent
costs are in parent_boundary_instructions; parent_instructions is retained
pre-Square128 history. There are 454 faster states, no increases or new
losses, and 11434 loss pairs in each version. Original153 stays 119 strict
and 34 slower. No new Qfplib win is claimed.

The author's frozen result/HANDOFF incorrectly used the pilot's 4-169 range.
Separate corrigendum 729a5e18… binds the frozen/raw files and the two actual
3728-to-3548 witnesses. The correct full-corpus range is 4-180 instructions.
Those witnesses were independently executed in both SIO states. Frozen files
remain intact.

Own qualified execution comprises 320 bare ARM calls on 160 cases, plus 324
public ARM calls on 27 pairs in both SIO states (25 directed MPFR inputs and
2 sNaN policy shortcuts). All 24 midpoint bytes, returned sides, register
preservation, SP/PC, input/cell immutability and write bounds passed. Bare
cases cover both inverse modes, all eight production denominators and all
16 NZCV patterns. All 58 nonzero decisions have separate exact integer/dyadic
endpoint proofs. All three real Qfplib compositions remain in the public
output, including wrong results and costs. These are bounded checks, not a
second complete campaign.

An initial own bare attempt used an overbroad speed assertion for invalid
cells and stopped at cell zero. The identical exit semantics passed, but the
new guard took 20 versus 16 instructions. The successful broader guard check
records fourteen invalid cases at +4 and two at +7. Invalid-cell speed is not
qualified by the public speed claim. The failed attempt's reconstructed 290
calls are preserved separately and are not added to the qualified 644.
Three failed static reviewer preflights (symbol alias and register substring
assumptions) are also retained. None was a failed arithmetic comparison.

The bare peak was 212 to 156 bytes. The selected public peak was 968 in all
three images; the saved complete-corpus peak remains 2284 and the author's
fresh-control peak 2148. The parent's 716 on changed paths is a subset peak,
not a comparator for the complete corpus. No universal stack reduction is
claimed. The rejected80-bit filter, its 19221 bare / 1836 pilot ARM calls and
153 MPFR inputs remain separate and excluded.

Source merge/relink, actual integrated R12 and loader/layout guards remain
mandatory. A HOST byte-level negative control confirms the old 168-byte exp
overlay would overwrite 14 bytes of the table entry if loaded after the new
bank. No combined ELF is qualified. Reviewed507 remains 422; author unions
are not an integrated result. No device, network, Git or canonical operations
were used by this review.
