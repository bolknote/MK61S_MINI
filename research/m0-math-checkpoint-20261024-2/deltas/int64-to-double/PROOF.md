# Signed int64 entry: magnitude and path cost

Only the RP2040 `__aeabi_l2d` entry changes. All magnitude normalization,
53-bit packing, discarded-bit RNE, unsigned and 32-bit entry kernels remain
the parent implementations. The generic-M0 preprocessor branch keeps the
original signed entry verbatim.

Let the signed input be the two-word two's-complement integer H:L.
`ASR(H,31)<<31` forms the double sign bit in R2; its N flag selects the
negative path. For nonnegative inputs this takes the same three executed
instructions as the old `MOV zero; CMP H,zero; BPL` sequence, and reaches
the same magnitude code with identical R0/R1/R2. The old sign setup took
two additional instructions for negative inputs.

For negative H, complement H first. If the complement is nonzero, the
magnitude high word is `~H + (L==0)` and the low word is `-L mod2^32`.
This is exactly the old two-word negation. The new order retains the carry
from low RSBS through MOVS into ADCS. The high word cannot become zero:
`1 <= ~H <= 0x7fffffff`, hence the result is1..0x80000000. An unconditional
branch may enter the old high-word normalizer. This path saves one
instruction overall, including sign setup.

If `~H==0`, the integer is in [-2^32,-1]. When L!=0, its positive magnitude
is the nonzero32-bit `-L`. The narrow normalizer is safe directly, with
the negative sign in R1. No high-word ADC or repeated magnitude-zero check
is necessary. This path saves five instructions. For L==0, the value is
exactly -2^32: the explicit high word1 / low word0 enters the old high-word
normalizer and saves one instruction. No negative integer reaches the
integer-zero return path.

Thus every input reaches the same parent rounding kernel with the same
magnitude/sign. No approximation, fallback, call, stack, memory access or
new literal/table is introduced. The code-cost saving is in the entry;
it does not depend on changing rounding behavior. Full-domain equality to
the parent's results follows from this partition, while comparison against
correct Qfplib is an observed finite test result, not exhaustive2^64 timing.

Public object section bytes and all four entry offsets exactly match the
executed standalone ELF. All other allocated sections and undefined
dependencies match the parent. Generic M0 and M4 compile controls match.
This is a source/object argument, not a whole-image or hardware acceptance.
