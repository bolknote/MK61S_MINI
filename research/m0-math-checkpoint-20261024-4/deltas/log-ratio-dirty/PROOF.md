# Exact log quotient when SIO is busy

The old domain is delta in[0,2^41] and odd den in[2049,4095]. The required
result is floor(H), H=delta*2^29/den. The sole source-level caller builds
den=2049+2*index for a ten-bit index and a dyadic half-segment distance.
The hardware-ready assembly source prefix and all callers remain unchanged.
The busy branch returns0 immediately when both numerator words are0.
This exact shortcut leaves both result registers0 and preserves SIO.
For nonzero numerators the busy branch adds three simple instructions.

The existing1024-entry log10 table already contains

    R=floor(2^75/den) & ~63.

certify.py checks every row with exact integer arithmetic. Thus
0<=2^75/den-R<64, so0<=H-delta*R/2^46<2. The existing Q46 product kernel
has absolute error strictly below4.5+2^-14. Its omitted limb products
sum to less than2^49+2^32; half-up rounding and the bias4 give that bound.
The seed q therefore differs from H by less than6.50006103515625.

Compute the signed exact remainder

    r=(delta<<29)-q*den.

Its magnitude is below6.500062*4095, less than2^15. Low32 multiplication
and subtraction followed by the target's signed32 interpretation recover
r exactly, despite the much larger original numerator. If r>=0, add
floor(r/den) to q; if r<0, subtract ceil(-r/den). Both produce floor(H)
exactly. A three-bit compare/subtract/ADC divider suffices, because the
correction magnitude is at most7. The ceiling numerator -r+den-1 is also
below2^15. All shifts/products in the correction fit unsigned32.

For delta=2^41 or2^41-1 a product is unnecessary. Since R is a multiple
of64, floor(delta*R/2^46) is respectively R>>5 or
(R>>5)-((R>>46)+1). The latter ceiling identity holds because R mod2^46
is nonzero for all1024 odd denominators (checked exactly). This seed is
at most the true H, with error below3; at most two comparisons/unit
increments recover floor(H). Its low32 remainder is positive and below
3*den. These shortcuts cover both endpoints for every table row, rather
than matching public input bit patterns. They need no additional data.

The new helper reads the existing table and product kernel, uses no SIO,
and introduces no data or compiler-runtime dependency. The log10 table
definition is made visible earlier in the RP2040 translation unit and
its later include is guarded. It is still emitted once with identical
bytes. Generic M0 and M4 preprocessing/allocated controls remain equal.

Object isolation checks all other allocated sections/tables and all
other functions in the shared.m0_pow_extension section. The slow helper
grows76->232 bytes (+156 object bytes); the assembly shortcut adds8 more.
Linked component allocation grows160 bytes because of section alignment.
Undefined dependency sets match.
The diagnostic fixture includes the original ratio assembly so its busy
branch resolves to the actual candidate helper. Control public counts
are checked against the pinned resident, preventing an accidental call
back to the old helper. SDK memcpy/memset bindings are pinned explicitly.

The bare execution fixture loads the component plus only its184-byte
product kernel capsule from the pinned resident, without full firmware
or ROM. All1024 denominators,39,000-scale boundary/random numerator
pairs and both SIO states are tested against unbounded integer floor
division. It checks the seed bound independently, ABI/SP/bounded writes
and zero SIO reads/writes. Public ln is checked separately against fresh
directed MPFR, Qfplib and the pinned parent in both states. These checks
do not establish a whole-library, physical-cycle or independent review GO.
