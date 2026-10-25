# Exact midpoint boundary evaluation with the accepted square schedule

This replaces the body of the private `root128_boundary` entry. It retains
128-bit centers, the old 32-bit radius field and every final comparison rule.
The previous inline square used the same `+16` nonzero-low radius policy as
`pow_integer128_square`. It did not benefit from the newer scheduled kernel.

For a valid positive normal candidate cell c, the exact midpoint coefficient is
`C=2*((c&Fraction)|Hidden)+1` (54 bits). Both bodies initialize the identical
24-byte object: `high=C<<10`, `low=0`, exponent `int(c>>52)-1023`, radius zero.
The new h0 formula `(low32(c)<<11)|1024` is exactly the lower half of C<<10;
the high-word formula retains the hidden bit and the lower word's carry bits.
The low64 and radius receive explicit zero stores, with no memset dependency.

Both loops square the midpoint once per `n>1; n>>=1`. The production callers
provide denominators1,2,4,...,128. The old inline transform is
P=H²+2*old_approx_high64(L,H), radius `2*radius+(L?16:bool(radius))`, followed
by the same normalization. The accepted new square kernel implements exactly
this transform, including all field bits. Induction over the identical loop
therefore establishes identical complete midpoint objects, including radii.

For noninverse powers, both bodies pass the original input power and identical
midpoint to the same retained `root128_compare`. For inverse powers, both call
the same retained `pow_integer128_multiply(midpoint,power)` and apply exactly
the old exponent, high64 and low64/radius comparisons against1. The split-word
high comparison is equivalent to `high>(1ULL<<63)` and `l1!=0 || l0>radius`
is equivalent to `low64>uint64(radius)`. The `uint64(0)-radius` threshold for
exponent−1 is unchanged, including radius zero. Invalid cell ranges return0
in both implementations. A zero side remains undecided. No public RNE enclosure,
packing rule, NaN policy, approximation, domain or fallback is altered.

The full old532-byte resident slot stays at0x10150000. Its replacement is a
two-instruction `LDR R3,literal; BX R3` tail transition to the compiled body;
the remaining524 bytes are unused padding. It preserves R0–R2, the caller's
LR and SP, and the uint64 cell at incoming SP. R3 is an unused ABI argument
slot because the aligned uint64 fourth argument is on the stack. The body
uses ordinary PCS and returns only int32 in R0. No additional private R12
return contract exists for this function. The separate shared-product R12
consumer is unchanged and still needs its actual merged-image guard.

The control front is byte-identical to the old resident532 bytes. Actual full
RP2040 assembly objects differ only in that slot and its own relocation.
The diagnostic body is below0x10200000 and does not overlap any loaded ELF
allocation. Production placement still requires the normal linker/layout check.
Other resident code, tables, scratch reservations, addresses and veneers are
unchanged. Default M0 and M4 soft/hard selected assembly controls are equal;
the additional translation unit is entirely guarded by the RP2040 macro.

The bare check loads only old/new fronts, the actual old490-byte multiply,
372-byte compare, and the accepted232-byte square plus94-byte helper. The
multiply section has two additional unreachable GAS alignment bytes. There
is no firmware, ROM or arithmetic model in those machines. Three thousand
constructed and random cases exercise both inverse modes and all denominators
at near and distant boundaries. Both returned sides and all24 bytes of each
midpoint operand match. Every nonzero side is also verified independently
against exact integer/dyadic midpoint powers and the entire supplied power
interval. All16 NZCV values, noisy R3/R12, PCS/SP/PC, bounded writes and unchanged
input/cell are checked. The observed boundary-call peak shrinks212→156 bytes.

The complete120980-pair union is freshly replayed in both SIO states. Every
changed path also freshly executes the parent and compares all24 midpoint
bytes and actual parent costs. Unchanged paths require exactly the saved parent
cost. Fresh directed MPFR controls execute parent, layout control, candidate
and all three actual Qfplib compositions; wrong reference outputs are retained.
The author qualification is separate from independent review and integration.

## Rejected narrower filter

The preceding80-bit filter passed exact interval tests but failed its speed
purpose: every one of56 original public boundary checks declined and added
262–904 instructions. Exact dyadic calculations measured relative gaps of
2^-97 through2^-108. Even an ideal96-bit truncated model did not decide those
cases; the128-bit model did. The rejected trial's19221 bare and1836 pilot ARM
calls and153 pilot MPFR validations are excluded from this component's counts.
Its records remain separate. The present change retains full128-bit precision.
