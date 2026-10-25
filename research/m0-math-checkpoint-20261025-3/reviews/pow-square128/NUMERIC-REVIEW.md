The authoritative source parent is the independently accepted table-product
component, not the separately accepted near-one sibling. This change replaces
only the square128 function and retains its original310-byte fixed slot.
Its actual function is232 bytes;78 bytes of padding are never executed.

The24-byte object contains H64,L64,exponent32,radius32. Treat the unchanged
94-byte helper result as an arbitrary U64 C, selected only if L!=0. The old
and new transforms produce P=H^2+2C modulo2^128. Both produce
E=2*radius+(16 if L!=0 else bool(radius)) modulo2^32 and double the exponent.
If P.bit127 is set, exponent is incremented; otherwise P and E shift left.
Thus equivalence preserves all24 output bytes, including wrap and invalid
input bit patterns, without inventing a different interval-radius policy.

For square32, x=a+b*2^16. Three products give a^2,ab,b^2. Low is
a^2+(ab<<17) modulo2^32, and high is b^2+(ab>>15)+the low addition carry.
This is exactly x^2; the final high fits32 bits. For cross32, x=a+bB,y=c+dB,
B=2^16, use p=ac,t=bc+(p>>16),v=ad+(t modB). Both t and v are at most
B^2-B, hence fit32. The reconstructed low/high equal xy exactly.

Splitting H=u+v*2^32, the two square32 operations plus two explicit ADD/ADC
chains place 2uv at bit32 between u^2 and v^2. A second pair of four-word
carry chains adds the same helper C twice. These are exact unsigned modular
identities. The remaining sign-bit test and four-word LSLS/ADC shift match
the old normalization. CMP radius,#1 yields carry bool(radius), even when
its sign bit is set. The old upper exponent OR1 equals the new ADD1 because
the doubled exponent is even. No old bound or fallback was weakened.

Fresh unit disassembly independently gives four old/new path costs:
129/94,116/89,195/154,182/149. The kernel frames are48/40 bytes; the unchanged
leaf helper adds20, giving68/60. Actual bounded Thumb execution checks these
classes, all24 data bytes, arbitrary exponent/radius fields, all16 incoming
NZCV values, noisy volatile registers, R4-R11, SP/PC and bounded writes.
The two actual resident callers overwrite R0 and set their own flags before
use, consistent with ordinary void PCS. There is no R12 extra result here.

Public bounded execution preserves parent/control/candidate raw results and
all kernel-input sequences, with total instruction reduction exactly the sum
of measured per-kernel reductions. All three Qfplib compositions and incorrect
outputs remain explicit under strict quiet-NaN classification. The unchanged
public RNE enclosures are inherited; general-pow totality is not established.

The independent saved-data recount does not rerun the large campaign. On the
same116468 old pairs, losses10853->10850; on120980 expanded pairs,
11449->11434. The596 additional loss pairs were preexisting. Old3 and expanded15
fixes are strict in both SIO states against every correct reference. There
are no instruction increases. The full old corpus still observes2284 stack
bytes, while new controls observe2148 for parent/control/candidate. These
different corpora do not establish a universal full-call stack reduction.

R2 is a new valid seal over byte copies. The original seal stays rejected:
its empty finalize.log pin disagreed with the completed376-byte log. The only
copy differences are the appended HANDOFF and amplified lineage metadata:
all1516 old external pins are retained,69 historical producer/sealer pins are
added. Sources,binaries,raw data,proofs and result bytes are unchanged. Copying
adds no ARM/MPFR calls. The historical7bf WIP checkpoint is not rewritten.

The separately accepted near-one source still needs merging and relinking.
The old168-byte exp overlay still destroys the first14 bytes of the table
entry. Future actual linked R12, loader/layout and overlay guards remain
mandatory. This private unit/overlay gives no integration, hardware, physical
cycle, whole507, main or release approval; reviewed507 remains422.
