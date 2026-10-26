# Exact endpoint predicate with the high-word power path first

Private child of the frozen near-ln directional component. The only
source delta replaces delta>=2^41-1 by an equivalent uint32 predicate:

    high32(delta)==512 ||
      (low32(delta)+1 modulo2^32==0 && high32(delta)==511).

For the original domain0<=delta<=2^41, high<511 means neither endpoint;
high511 selects exactly low0xffffffff; high512 forces low0 and selects
the other endpoint. These cases exhaust all513 high words. The unsigned
low addition is defined modulo2^32. No approximation, seed, polynomial,
correction, rounding rule, special value or other domain has changed.
certify.py reconstructs the entire parent's header by replacing this
one condition and checks all high-word classes plus random/boundary data.

The old64-bit comparison lowered to extra high/low checks before the
general seed. Splitting that exact condition removes four instructions
on the three former722-instruction DIRTY cases. The high-word test comes
first so the dyadic endpoint keeps its early route. The rejected low-word
first experiment saved six ordinary instructions but added five on ln2;
its source/build/probe records remain in the separate trial directory
../m0-log-ratio-endpoint-entry-20261024/trials/low-first. The selected
short probe gives718 versus correct Qfplib719 for all three cases and
ln2 DIRTY610 versus613parent and711Qfplib, with no probe regression.

The direct bare ARM helper test covers every1024 denominator, both SIO
states, all original seed cases and additional low-word wraps at high
words1,255,510,511,512. Every result is checked against unbounded integer
floor(delta*2^29/den), with PCS/SP/bounded writes and zero SIO accesses.
Only the component and its existing184-byte product capsule are mapped;
no firmware or ROM is loaded. The capsule hash/source proof is inherited
from the accepted exact-quotient packet, not a new arbitrary dependency.

The public corpus retains every parent's65880 state case and adds
general-kernel low-word-wrap controls. All are freshly profiled in READY
and DIRTY against the parent, V164, Qfplib and directed MPFR. Counts are
executed instructions, not physical cycles. Raw wrong Qfplib answers,
remaining deficits and any regressions are retained in qualification.

Only the helper body in its shared.m0_pow_extension section is allowed
to change. Other shared functions, near-ln code, all other allocated
sections/tables/dependencies, the ASM object and generic/M4 controls are
checked. Full CPP/ASM objects and the complete ELF independently rebuild.
This does not integrate math into canonical firmware or claim hardware
acceptance. Other operations, general pow totality and the full original
goal remain open.
