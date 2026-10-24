# Exact small-low-limb log quotient

Private RP2040 child of the accepted endpoint predicate. For signed low
word ell-64..64, delta=F*2^32+ell, reuse the existing reciprocal and six
small products to get a nonnegative underestimate within5Q70 units.
Three remainder bits produce exact floor(H). The generic path now adds
a sign-extended correction, avoiding a wasted U64 sum before subtraction.
All other quotient/polynomial/table/rounding algorithms remain unchanged.

Host uint128 exhaustion covers all67,634,176valid pairs,1024den513F129ell,
with exact independent quotient/remainder and digest69f36adcd7428ad1.
These are not ARM calls. Fresh bare ARM covers197564pairs/790256calls,
all1024den/bothSIO/familyandguardedges:0wrong,0SIOaccesses,PCS/SP/bounded
writes pass. Only component+accepted184Bproduct capsule, nofirmware/ROM.
Fresh public34438unique/68876allprofiled states/275504ARM:0wrongMPFR4.2.2,
raw parent NaN policy/callerSIO/PCS/SP/bounds pass. All66172parentcounts
reproduce. Qualified ARM total1,065,760, not counting discarded trials.

All28former general DIRTY losses now beat correct Qfplib; on the sameold
corpus73raw→45. The broader guard/ordinary controls expose150preexisting
parent losses, giving expandedparent223raw→child68raw/113states:
155rawfixed,0newlyintroduced.23new-control losses remain alongside the
old45. All wrong-reference outputs/losses/regressions are preserved.
Examples DIRTY:718→647vsQfp716;719→644vs689;713→676vs683.
The one new guard-edge loss in an earlier full trial was addressed by
the signed-return optimization: former trial715 now712vsQfp713.

READY34438counts identical. DIRTY4796faster22863equal6779slower; each
regression is3or4instructions. ln2DIRTY613 versus parent610/Qfplib711
is explicitly a3instruction power-path regression. Publicstack640same;
helper76vs68. Code+212Bobject/+216Blinked, only slowhelper232→444B.
No newtables/RAM/libgcc/deps. Other shared bytes/functions and allocated
sections/tables, ratioASM and genericM0/M4controls match (not wholeM4FW).
WholeCPP/ASM/ELF rebuildbyteexact. Near source/object body/table bytes
match parent; linked addresses relocate, not claimed identical. No mathROM.

Source:af83817a78b261621a638c5cc3436bfd63ef57371d999766dfad2a50733dcef7
ELF:c0000b4a468cdb80228fab332978f276a21cf5e229fa1abe7622a287ef396297
Object:bd694a4bc008a9a3de0555f190f1b9aa451c6dffceba7dfa06bb11b8eb68f019

Hold packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. Historical ln
remains6/10fixed4open. Other operations/general pow totality/the original
full math goal remain OPEN.
