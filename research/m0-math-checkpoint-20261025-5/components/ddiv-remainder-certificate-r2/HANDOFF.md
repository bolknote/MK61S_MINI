# Bare exact remainder-sign macro: qualification complete

The exact model is the complete uint32 high product and low-word borrow.
100800 actual test cases,201600 control/candidate ARM calls. Both sign
discontinuities and all16 NZCV combinations are tested. Live R1/R12,
PCS/SP/PC and only20B wrapper stack writes are checked. Certified cases
save12/15 wrapper instructions; uncertain cases add8. This is not a public
division speed claim. The macro is shared byte-for-byte with the new private
reciprocal component. No MPFR or device call was made. The earlier338416
integer-model cases are inherited from the archived source parent, not new
calls in this packet. Its integer proof covers the entire uint32 domain.
