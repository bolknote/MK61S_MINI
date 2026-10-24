# Bounded residual repair for atan rounding

This private delta extends the accepted packing/enclosure component.
It leaves its selector, reciprocal, ratio, polynomial, tables and fallback
unchanged. It is entered only when the parent's directional interval cannot
decide rounding, for non-inverted inputs with exponent -5 through -1 and
computed quotient `h <= 2^62 + 2^40`.

## Exact geometry and quotient residual

Let `N,D` be the original integer numerator/denominator, and
`H = (N/D)*2^64`, in Q70 angle units. No denominator halving occurs in
this domain. `D >= 2^59` and `D < 2^64`.

Nearest 1/64 grid selection gives `abs(x-index/64) <= 1/128`.
The accepted geometry identity gives
`N_normalized = 2^69*abs(x-index/64) <= 2^62`.
The parent's reciprocal and product bounds therefore imply
`abs(H-h) < 13/2 + B < 19 < 33`, where the pinned exact reciprocal
bound `B` is about 12.000004. This delta conservatively uses 33.

Compute `R = (N<<64) - h*D`. Since `abs(R) < 33*D < 2^70`, its
unique signed representative modulo 2^71 is exactly R. Only the low
64 product bits and seven high-word bits are needed.

For `h=al+2^32*ah`, `D=bl+2^32*bh`, form
`p=al*bl`, `t=ah*bl+(p>>32)` and `v=al*bh+(t mod2^32)`.
These intermediate sums fit unsigned64. Product low is
`(v<<32)|(p mod2^32)`; product high modulo2^32 is
`ah*bh+(t>>32)+(v>>32) mod2^32`. The high-high term thus needs one
32-bit multiplication. Subtract the low-word borrow and sign-extend
the seven remaining high-word bits. This recovers R without approximation.

## Short quotient and angle enclosure

Let `D0=floor(D/2^38) >= 2^20`, `R0=floor(abs(R)/2^38)` and
`q0=floor(R0/D0)`. Because `abs(R)<33*D`, `q0<=33`, and
`-33/2^20 < abs(R)/D-q0 < 1+1/2^20`.
The helper returns signed `delta = sign(R)*q0`.
A six-bit compare/subtract/ADC divider computes q0 exactly, uses no SIO,
and has no general division or compiler-runtime call.

The unchanged polynomial and table have error below 4.459 Q70 units on
`abs(h/2^70) <= 1/256+2^-30`. The quotient truncation contributes less
than `1+34/2^20`. Reusing the old polynomial changes the exact atan
correction by less than `33*(hcap+33/2^70)^2 < 1/1024` beyond the
linear delta. The exact Fraction sum is below 5.460, hence below6 Q70.
The original geometry sign determines whether delta is added or subtracted.

Repair is entered only within54 Q70 units of a binary64 midpoint.
`abs(delta)<=33` and every packing half-quantum is at least1024, so the
quantum index, binade and retained significand stay unchanged. Only the
rounding tail changes. A repaired midpoint distance of at least6 is safe
because all error bounds are strict; otherwise the original fallback runs.
The input sign, signed zero and NaN policy follow the unchanged public code.

## Evidence and limits

`certificate.json` contains exact rational bounds, not host floating-point
estimates. `helper-proof.json` compares actual ARM with unbounded Fraction
quotients and Python's exact truncated division, including all quotient
magnitudes0..33, positive/negative carries, ABI, bounded writes and both
SIO states. `qualification.json` replays the frozen public atan corpus
plus new h-cap, exponent and hard-input neighborhoods, with fresh MPFR
and raw Qfplib outcomes. It records parent count regressions explicitly.
`isolation.json` and `public-body-proof.json` bind this source to executed
bytes and check generic M0/M4 isolation and unchanged dependencies/tables.

These are instruction counts and software-emulator checks. They do not
provide physical cycle measurements, a combined firmware qualification,
independent review or complete the remaining whole-library math goal.
