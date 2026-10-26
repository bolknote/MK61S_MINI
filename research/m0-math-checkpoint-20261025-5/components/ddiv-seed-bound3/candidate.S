#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
#include "candidate-seed.inc"
.section .unit,"ax",%progbits
.p2align 2
.global unit_inline_seed
.type unit_inline_seed,%function
.thumb_func
unit_inline_seed:
 push {r4-r7,lr}
 reciprocal_seed_inline
 mov r0,r6
 pop {r4-r7,pc}
.size unit_inline_seed,.-unit_inline_seed
#include "inline-seed-table.inc"
#endif
.section .note.GNU-stack,"",%progbits
