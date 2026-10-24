Private RP2040 near-one exp candidate; accepted parent directed product e6ce7678,
independent TECH_GO0d6073f3 and ROOT7ec53f3c directly reverified. New review pending.

Same467366exp inputs:1896->196 speed losses,1700fixed. Full490031union214
=196old+18new measured preexisting; all428remaining states parent-bound,
36fresh parent ARM calls,0new losses. All old raw result bits identical,
0wrong. All16originalexp remain strictly faster in both SIO states.
Example3E9049F06E7592B7:18068->444vs494;3EC1BD399F566C29:2149->444vs544;
negativeBE99A94473BFE892:18448->467vs612. Power2^-16:438->426vs474.
Some5712parentstate cost increases retained(+1..44):5662still no slower
than correctQfp,34wrong-reference,16already lost.407820wrongQfpstate
outputs/costs retained; no nominal-domain filter. See raw gzip and bindings.

The new helper retains exact linear M and encloses the nonlinear correction
in input-ulp Q16 for e=-32..-12. Short high product keeps6terms, bit48
product9terms, square uses6MULS. Explicit full-source rational error guard
4*floor(Z/2^48)+32+extra+fifth_error; exact modular interval packing.
Declines use unchanged exp_refine(x,0). All operand bounds/carries/shift
ranges/coarse fifth and exact/15 proven in NUMERIC-PROOF/certificate.
104054bare arithmetic ARM checks including all16NZCV;74088literal pack
checks across21binades/both signs/carry/admission boundaries,0unsafe.

Full public validation:980062fresh candidate+45330fresh newQfp ARM;
934732parent/reference rows inherited, not fresh.490029actual directed
MPFR inputs+2sNaN shortcuts.2688log generations separate. Total qualified
fresh ARM1203570=1025392public+36parent+104054integer+74088pack.
Probes/trials/diagnostics not pooled; see VALIDATION-NOTES and archived trials.

Code/privateFlash+1136B,16480->17616; no new tables/globalRAM/
libgcc/ROMmath. Shared77product,168B RAMslot and every existing ASM source
unchanged. All other CPP allocated bytes/semantic relocs equal; selected
genericM0/M4soft/hard CPP equal;11whole object/ELF rebuilds byte-exact.
Public static frame96->88, new helper72; observed full exp peak744->808,
not a universal stack bound. One CPP file patch; no build-list changes.

PrivateR12 guard now reads fresh actual disassembly and validates producer
through2postcall instructions/zero-byte definition marker to actual88-
instruction consumer live range, unchanged real16BFlash tailveneer.
Builder automatically runs it;17negative AST controls pass. It must be
installed/adapted/rerun on each changed actual integrated object. Scalar
C prototype or this private receipt alone is insufficient for integration.

Original507author separate union unchanged423=417strict+6equal;84remain
(pow48/sin22/cos14,exp0). Reviewed422kept by ROOT instruction. Pow7901,
ln5 inherited separate qualifications, no fresh other-caller tests claimed.
Expandedexp214,FMA/general totality/combined integration/regression/physical
cycles/release remain open. No canonical/Git/USB/device/Flash/lease/EA9/
release mutations. Goal active; no hardware or production GO.
