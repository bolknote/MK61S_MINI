# Table-only exp product in RP2040 pow

This change preserves every returned bit of the previous scalar operation.
It does not weaken any existing pow enclosure or binary64 RNE decision.
It does not establish the previously open general-pow totality claim.

The three changed call sites load `q=exp_table[index]`, where
`index=unsigned(k)&511`. No arithmetic modifies q before passing it as A.
All other calls continue to use the original general entry. The actual
linked 512-entry read-only table is byte-identical to the frozen parent:
entry zero is exactly 2^62, and every other entry has nonzero low32.
Consequently the new entry's `A.low32==0` test implies A=2^62.
This is a private table-entry contract, not a test valid for arbitrary A.

If A.low32 is nonzero, CMP and the taken conditional branch preserve all
argument registers and enter the original 154-byte/77-instruction body.
That body is byte-identical at the original RAM address. Its scalar result,
stack behavior and extra retained fraction in R12 are unchanged. The two
additional instructions account for the complete generic cost increase.

If A=2^62, every omitted low product of the old kernel is zero. Its old
rounded high product is exactly

    (B >> 2) + ((B >> 1) & 1).

The internal product uses the same half-up tie rule as the old kernel;
it is not itself an IEEE floating-point operation. The later unchanged
enclosure/packing logic supplies the public binary64 RNE result.
The identity holds for every unsigned 64-bit B, not only the smaller
residuals reached by normal pow calls.

Write B=h*2^32+l. The new shifts and OR compute

    low  = ((h & 3) << 30) | (l >> 2)
    high = h >> 2.

These low-word fields do not overlap. LSR(l,2) sets C to bit1(l).
ORRS and MOVS preserve C on ARMv6-M. The two ADCS add that rounding bit,
including the carry into high. Thus the returned unsigned64 value equals
the old expression for every h,l. Incoming NZCV and R12 do not matter.
The complete dyadic path costs ten instructions and writes no stack.

The new dyadic path does not promise the old extra R12 fraction. Its
three table callers use the ordinary scalar U64 ABI and do not capture
that fraction. The exp consumer that does capture R12 still calls the
unchanged general entry. Its real original Flash-to-RAM wrapper and all
154 function bytes are unchanged. Any future integrated release must
still rerun its required actual-image R12 guard; this component is not
integration acceptance.

The new Flash wrapper has exactly the old real wrapper's first twelve
bytes; only its final target word changes. Both execute five instructions.
It restores SP before entering the product. Public pow cost therefore
changes by `2*g - 67*d`, where g and d are its actual generic-table and
dyadic-table calls. Every other product call keeps its old 77 instructions.

The accepted R ancestor used the equivalent 84-instruction kernel. If n
is the actual number of logical old product calls, then

    candidate_cost = R_cost - 7*n + 2*g - 67*d.

Here n>=g+d, so this candidate never increases R's cost. The full inherited
111,912-pair corpus checks this identity for every freshly executed state.
All 10,081 previously fresh C77 sensitive-state costs are also checked.
The saved R, C77 and Qfplib records are inherited evidence, not new calls.
Fresh parent/control execution on additional MPFR controls checks the
unchanged calling-layout costs independently.

CPP allocated bytes and constants are identical; only three call
relocations change. Both source-level default M0 and M4 controls remain
identical. The new code needs no new table, global data or libgcc entry.
The original general product still occupies its original address; the
table entry uses existing dead padding before the RAM veneer area. The
reserved scratch extent remains 4,080 bytes. Private linking relocates
existing code and constants for diagnosis; integrated firmware GC/size,
physical cycles and hardware acceptance are separate open work.
