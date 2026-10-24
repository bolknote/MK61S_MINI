The input of the new helper is positive normal binary64. Its wrapper keeps
negative, subnormal, zero and nonfinite inputs in the unchanged dispatcher.
This document proves returned binary64 RNE for that normal-input helper;
it does not prove general `pow` termination or universal relative speed.

Write the normalized integer mantissa as `m in [2^52,2^53)`, with exponent
parity `p in {0,1}`. Cell index `i` is its top eight fraction bits. Set
`d=513+2i`, `c=d*2^43`, `u=(m-c)/c`. Then `|u|<=1/d<=1/513`.

The existing512 seed integers `B` are unchanged. For every row, the exact
integer inequalities in certificate.json prove that B is RNE of
`s0=2^32/sqrt(d*2^p/512)`. In particular `|B-s0|<1/2` and `B<2^32`.

For B's upper/lower16-bit words H,L, the two-MUL expression
`R=(H*H+((L*H)>>15))>>(9-p)` is floor(2^32/d) in511 rows and one less
in one row. All512 exact comparisons are recorded. Consequently for ANY
uint32 numerator N, `q0=floor(N*R/2^32)` never exceeds floor(N/d), and
its integer underestimate is at most2. `q0*d<=N<2^32`; the remainder
multiplication cannot overflow. Two conditional subtractions recover the
exact quotient. The inline runtime and isolated tested quotient macro have
identical emitted instruction bytes, including all carry branches.

For nonzero distance, the old coordinate is
`t=floor((abs(m-c)-1)/(d*2^11))`; zero distance gives t=0. Because the
distance is integral, `0<=2^32*|u|-t<=1`. The new quotient gives exactly
the same t. Let `z=floor(t^2/2^32)` and
`w=floor(z*floor(t/2^16)/2^16)`. They match the old C code exactly.

The polynomial is the degree-three Taylor polynomial of `(1+u)^(-1/2)`.
Its integer quadratic coefficient Q is `floor((3*z+4)/8)`. Roundoff on
the eight residues of3z modulo8 is in[-3/8,1/2]; including z's truncation
gives Q error in(-3/4,1/2]. The cubic coefficient C is
`floor((5*w+8)/16)`. Its sixteen roundoff residues lie in[-7/16,1/2].
Furthermore, with `v=1/513`,
`0<=t^3/2^64-w<1+v+2^16*v^2`.

In seed-integer units the following uniform absolute bounds therefore hold:

| Source | Bound |
|---|---|
| Seed-table error | `1/(2*(1-v))` |
| Coordinate quantization | `1/(2*(1-v)^2)` |
| Order-four Taylor remainder | `(35/128)*2^32*v^4/(1-v)^5` |
| Quadratic integer error | `3/4` |
| Cubic integer error | `7/16+(5/16)*(1+v+2^16*v^2)` |
| Final seed rounding | `1/2` |

The sum is855035209253/275952697344, less than25/8. Integer powers in
the table and derivative factors deliberately enlarge the half-integer
powers: `(1-v)^(-1/2)<(1-v)^(-1)`, `(1-v)^(-3/2)<(1-v)^(-2)`,
and `(1-v)^(-9/2)<(1-v)^(-5)`. The coefficient35/128 is the fourth
derivative coefficient divided by4!. Saturation at2^32-1 cannot enlarge
absolute seed error beyond max(previous error,1), because the true seed
never exceeds2^32.

All intermediate widths are bounded: `t<2^32/513<2^23`,
`z<2^32/513^2<2^14`, `z*(t>>16)<2^21`, `5*w<2^16` and the
signed correction magnitude is below2^24. For t>=2,
`2Q<=3*t^2/(4*2^32)+1<t`; for t=0,1, Q=C=0. Thus the branch which
forms magnitude from t+2C and2Q is exactly the old signed delta's absolute
value, including zero. Adding2^32 to the correction product then shifting
33 equals `(high32(product)+1)>>1`, with no possible overflow.

Put `A=m<<(10+p)`, `s=2^63/sqrt(A)`, so `2^31<s<=2^32`. Let S be
the final integer seed, E=S-s and T=s*2^31 the exact output coordinate.
The ideal Newton point is
`T-E^2*(3*s+E)*2^30/s^2`. Its nonnegative downward error is less than
`(25/8)^2*(3/2+(25/8)/2^32)`. The existing high-product expression
discards two fractional cross terms and the low-low term. Each is in[0,1),
so its underestimate is less than3. Multiplication by S/2^32 is below1.
The final floor can lower the point by less than1. Hence the actual integer
point q satisfies:

`T - 15.648437507106 < q < T + 3`, in particular `|q-T|<16`.

Binary64 midpoints in this coordinate are512 modulo1024. If q's tail is
at most496, T is below its midpoint; if tail is at least515, T is above it.
Only the18 integer tails[497,514] remain ambiguous. They retain the
original exact161-bit midpoint comparison and tie rule. The accepted
shortcut excludes ties, so half-up equals RNE. The normalized result is
in[1/2,1]; crossing an endpoint by fewer than16 coordinate units still
rounds to that endpoint. Exponent scaling is exact and always yields a
normal result for positive normal binary64 inputs.

The common final factor words0x7fffffff and0x80000000 use their exact
shift/subtract products. Every other word takes the full32x32 product;
these branches make no assumption that other factor words are impossible.

The full ASM saves64 bytes and restores the ARM PCS, including on the
original boundary and fallback paths. The boundary alias exports the
unchanged static C helper without storing data or changing its code. All
other C++ code/data/relocations and generic M0/M4 selected translation
units are checked against the parent. Physical cycles, integrated firmware
and independent acceptance remain separate work.
