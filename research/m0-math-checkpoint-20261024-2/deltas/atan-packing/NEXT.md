# Next original-goal work: the remaining atan refinement cost

This file is a proposal, not implemented or measured. The current reviewed
target must remain immutable; implement separately if proceeding.

The two remaining magnitudes have true midpoint distances9.8003239047 and
14.0662930026 Q70 units. Q70 table precision is sufficient; adding a large
angle table is unnecessary. Their current quotient errors are4.08488 and
4.65813 Q70 units. The broad quotient error enclosure is what prevents a
fast answer and triggers duplicate refinement/CORE-MATH.

A cheap bounded residual correction can reuse the existing angle:

1. Compute exact p=h*d with the existing128-bit integer multiply. The
   signed residual is R=(n<<64)-p. The inherited quotient bound gives
   abs(R)<33*d, so its high magnitude word is at most32.
2. Set D0=d>>38, R0=abs(R)>>38. For the non-inverted e=-5..-1 domain,
   D0>=2^20, R0 fits32 bits. One existing interrupt-safe32-bit division
   gives q0=floor(R0/D0), at most33. It approximates abs(R)/d to within
   1+34/2^20. Apply the residual sign to obtain delta_h.
3. Add/subtract delta_h from the Q70 angle according to reduction sign.
   The derivative difference from1 contributes less than1/1024 Q70 when
   h<=2^62+2^40. The old polynomial/table error without quotient error is
   below4.46 Q70 here. A new strictly valid radius6 Q70 appears sufficient;
   derive it with exact fractions before execution.
4. The repair is reached only within54 Q70 units of a midpoint. Since
   delta_h<=33 and the minimum half-quantum is1024, the quantum index,
   binade and truncated53-bit significand cannot change. Only the tail
   and final rounding increment need updating; reuse the existing pack
   metadata instead of another general pack.

This requires retaining numerator/denominator words across the first
stage. Measure register/stack spills and every unaffected path; do not
claim the estimated speed. Keep the original fallback when the tightened
interval is undecided. No input-specific return values or relaxed rounding.
