# Remaining atan work after the four-input residual repair

The full functional replay found22 unique CORE-MATH inputs. Twenty of
them had not been profiled by the old speed subset. `cold-profile.json`
measures every observed CORE route; eleven raw inputs still lose to a
correct Qfplib answer. Both SIO states are retained. These deficits already
exist in the accepted parent. Do not call atan speed-complete because the
original32,084 profiled rows have zero losses. `speed-proof.json` joins
them with40 additional distinct profiled state rows and retains22 losses.

`diagnosis.json` / `diagnose-cold.py` explain the unchanged first stage.
Several remaining inputs have exponent-6 (the current repair excludes
the denominator-halving case), one magnitude is inverted, and some have
reduced h above1/256. The largest h needs a more accurate polynomial,
not just a better quotient: the omitted positive h^9/9 reaches about14.23
Q70 units near1/128. Blindly raising the existing radius cannot fix this.

Potential next steps, not implemented or qualified in this packet:

1. The current exact bound is5.45951 Q70. Adding a conservative1/2 for
   either denominator halving or the second table value remains below6.
   The original selector/ratio proof has global quotient error<33 and
   h<1/128. Inverted denominators can be as small as2^58; the truncated
   divisor still satisfies D0>=2^20. This can extend the cheap repair to
   small h in the two other geometry classes without a new table.
2. Correct the fifth term's discarded cross products and include h^9/9
   only in an undecided cold path. For C3,Z in Q70, the missing fifth
   product is approximately
   `(C3_hi*Z_lo)/2^53 + (C3_lo*Z_hi)/2^46`, with17/24-bit split points.
   Two16x16 products can approximate this cheaply. A ninth coefficient
   can use `(C7>>6)*(Z>>40)` then a24-bit shift; the discarded-product
   error is small. Prove every error before adding a rounding gate.
3. Separate term roundings are expensive in the error budget. Their exact
   small remainders can be combined without a general division. With
   r3=C3-3*T3, r5=C5-5*T5, r7=C7-7*T7, r9=C9-9*T9, the correction to
   `-T3+T5-T7+T9` is `(-105*r3+63*r5-45*r7+35*r9)/315`.
   Its nearest integer is selected by thresholds158/473 when the
   remainders have the usual nearest-division ranges. This is a design
   hypothesis; current code does not use or claim its bound.

Any new code must be developed in a new child directory after this packet
is handed off. Preserve this source, raw outcomes and four confirmed wins.
Profile all observed repair/CORE routes in future full functional runs.
Keep all historical507 inputs and all raw incorrect Qfplib results intact.
