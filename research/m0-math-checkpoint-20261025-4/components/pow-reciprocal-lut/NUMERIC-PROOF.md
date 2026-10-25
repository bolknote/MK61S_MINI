# Exact small-table seed for the existing division path

The new implementation changes only the private seed suffix. The complete
hardware body, software setup, saved frame, R12 contract, correction and
RNE tail, root BL and all other resident bytes remain identical. The seed
still returns floor((2^32-1)/D) for every65536<=D<=131071, preserves R1/R12
and callee-saved registers, and writes no stack or memory. Its new R3
clobber is permitted by the private caller, which saves/restores R0..R3.

For index i=(D>>9)-128, table[i] is the exact integer
u=floor(2^32/(65536+512*i+256)). The128 uint16 constants occupy256B.
Let x=ceil(D/2), p=x*u, e=floor((p-2^31)/2^16).
The signed folded product ASR17((2p) mod2^32) is exactly e because the
complete-domain integer model proves |p-2^31|<2^30. The next signed product
u*e fits int32. The approximate quotient is q=u-floor(u*e/2^15).

For all65536 inputs the exact integer model finds q-floor(N/D) in[-1,3],
where N=2^32-1. The actual residual N-qD fits signed32. Consequently the
ARM low32 MUL followed by MVN gives the exact signed residual even if the
full qD crosses2^32. If it is negative, decrement q and add D until the
residual is nonnegative; if it is >=D, increment q and subtract D. Each
step preserves qD+r=N. At most three downward or one upward correction is
needed. On exit0<=r<D, which proves the exact quotient. No approximation
or new error bound enters binary64 arithmetic: its original integer seed,
Newton steps and RNE remainder decisions are reproduced exactly.

The bare ARM campaign executes the entire divisor domain and all16 NZCV
values around each table boundary, with noisy volatiles and R12. All four
explored variants return exact quotients. The selected128-bin floor variant
has the lowest measured worst latency:20–27 instructions, versus82–97.
The current public corpus predicts the same nine fixes for all variants;
that sample does not select the implementation. A preliminary sample-only
selection chose a smaller but slower variant and was retained as history.
The final selection uses the complete-domain worst latency, then mean and
allocation. It does not change or rerun the bare numerical evidence.

The selected routine has56B of instructions plus256B of constants:312B
total,118B more than the194B old unrolled divider. The private division
section grows1050->1168B. These are new mathematical table values, not
global RAM. There are no new libgcc dependencies. The linked312B suffix
matches its tested bare image byte for byte. Default M0/M4 seed objects
are empty, and their selected root controls are unchanged.

All parent restrictions remain: this is a private pow reciprocal caller,
not a replacement of every resident ddiv caller, not a standalone C ABI
for the guarded continuation, and not an integrated firmware. Source
merge/relink, actual integrated R12/loader/layout guards, the14B old-overlay
hazard, physical cycles, remaining needed math and general pow totality
remain outside this component. Public qualification, raw Qfplib results
and fresh-call exclusions are recorded separately. The overall goal is
not complete.
