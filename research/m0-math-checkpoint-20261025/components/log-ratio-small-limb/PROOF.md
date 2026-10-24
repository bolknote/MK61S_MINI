# Exact quotient for a small signed low limb

Private RP2040 child of the accepted endpoint-predicate component. The
only new arithmetic family is delta=F*2^32+ell, F0..512, ell-64..64,
with0<=delta<=2^41. The uint32(delta)+64<=128 test detects exactly this
signed low-word range. Both old endpoints imply this test, so their
existing path can remain inside the guard. The endpoint's two booleans
are added as uint32 before adding their sum0..2 to the U64 quotient.
This grouping is mathematically identical. The generic retained-product
seed/correction and every other parent header byte are reconstructed by
certify.py after removing the new family, grouping and signed-return form.

Use the existing table R=floor(2^75/den)&~63 for every odd2049..4095.
All1024 actual reciprocals are checked in the host-domain producer.
The exact reduced target is H=delta*2^29/den. Compute

    A=floor(F*R/2^14),
    L=floor(abs(ell)*(R>>32)/2^14),
    seed=ell>=0 ? A+L : A-L-2.

A uses four exact16-bit limb products and carries. F0 and512 admit zero
and R>>5 shortcuts. L uses two uint32 products after a14-bit split:
(Rhi>>14)*magnitude+((Rhi&16383)*magnitude>>14). Intermediates remain
well below2^32. The combined subtraction A-U64(L+2) is safe because
L<2^24 and negative ell implies F>=1 and A>=2^49.

Let P=delta*R/2^46. Existing reciprocal quantization gives0<=H-P<2.
Write F*R/2^14=A+alpha, abs(ell)*Rhi/2^14=L+beta with alpha,beta in[0,1),
and eta=abs(ell)*(Rmod2^32)/2^46 in[0,1/256). For positive ell,

    P-seed=alpha+beta+eta, so0<=H-seed<4+1/256<5.

For negative ell,

    P-seed=alpha-beta-eta+2, so1-1/256<H-seed<5.

Thus seed never exceeds floor(H), and exact integer correction is0..4.
The true remainder(delta*2^29-seed*den) is nonnegative and<5*den<2^15;
the source recovers it by defined uint32 modular multiplication/subtract.
Three ordinary quotient-bit compare/subtract/ADC steps at4den,2den,den
recover exactly floor(H). There is no new division, table, global RAM,
wide runtime multiply or SIO operation.

The host C++ test exhausts all67,634,176 valid combinations of1024den,
513F and129ell. It independently checks each limb result, one-sided
seed error, recovered remainder and final quotient against uint128 floor
division. Maximum observed limb intermediate33,538,055; maximum error
remainder17233/3493<5. The histogram includes336174 corrections of4,
so the high quotient bit is necessary. The deterministic full-domain
digest is69f36adcd7428ad1. These are host integer cases, not ARM calls.

The actual bare ARM helper tests197564pairs/790256calls, every1024den,
both SIO states, original cases, family endpoints and +/-65 guards.
Every helper result equals unbounded integer floor(H); PCS/SP/bounded
writes and both SIO states pass, with zero SIO accesses. Only the new
component and the accepted184-byte product capsule are mapped, with no
firmware or ROM. Direct helper peak stack is retained in helper-proof.json against the parent's68 bytes.

The chosen source is the readable hoisted guard without an opaque asm
barrier, plus an exact signed-return optimization on the generic path.
The original return generated an unused64-bit sum before subtracting on
negative correction. With correction0..7, sign-extending +/-correction
then adding it to U64 q is identical modulo2^64 and avoids that work.
The first full corpus found one new speed deficit at the -65 guard edge,
715 versus713correct Qfplib; this generic optimization addresses it,
with a fresh complete qualification required after the change.
 Earlier variants are retained under trials. The first two-
product version still beat Qfplib on all28 known general losses but
added8..9 ordinary instructions. Hoisting reduced that to2..3 in the
512-input probe. An opaque barrier/handwritten endpoint correction then
added one instruction on eleven probe states without any measured gain,
so it was rejected despite saving eight code bytes. Selected ln2 DIRTY
cost is613 versus parent610 and correct Qfplib711; that three-instruction
power-path regression is explicit, not hidden.

Only the slow helper body in.m0_pow_extension changes, with its alignment region growing from232 to444 bytes.
All shared bytes outside that helper/alignment region, other allocated sections/tables,
undefined dependencies, ratio ASM and generic/M4 controls are checked.
The public CPP/ASM objects and entire ELF rebuild byte-exactly. The near
source/allocated object body and actual table bytes stay unchanged;
linked addresses/pointers relocate by the code growth, so old linked
address identity is not claimed. Full public qualification separately
checks the new linked component against parent/V164/Qfplib and MPFR.

Public tests retain every parent's66172 state case and add family and
guard boundaries plus512 ordinary controls. Every input is profiled in
READY/DIRTY, including raw wrong Qfplib results. Remaining losses and
parent regressions must be retained. Counts are instructions, not
physical cycles. Whole-ln speed, other operations, general pow totality,
canonical integration and hardware acceptance remain open.
