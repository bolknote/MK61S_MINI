# Exact seed correction bounded by three downward steps

The fixed table estimate error is[-1,3] for every65536 D. Negative residual
requires one,two or three decrements. One explicit decrement exits at BPL
for error1; a second ADD supplies unsigned carry for SBC with private R0=0.
The exact floor quotient is unchanged. Only error3 leaves R7 residual minusD,
which is dead before the production second product. This is not a generic
seed ABI: raw R0 must be zero. Shared production macro tested for all65536D
under every16NZCV:1048576tests/2097152ARM. All R0/R1/R2/R3/R5/R12/SP and PCS,
SP/PC/only20B wrapper writes checked.18592unit cases save3 instructions,
1029984 unchanged;0increases. The branch direction for error1 changes, so
these are instruction counts, not measured cycles. No MPFR/device call.
