.syntax unified
.cpu cortex-m0plus
.thumb
.macro sqrt64_polynomial
 asrs r4,r2,#4
 muls r3,r4
 asrs r3,#16
 adds r1,r3
 lsls r3,r1,#20
 lsrs r3,#20
 muls r3,r2
 asrs r3,#20
 asrs r1,#12
 muls r1,r2
 asrs r1,#8
 adds r1,r3
 adds r0,r1
.endm

// Exact 32-bit square: R0 is retained, R4:R3 is the result.
.macro sqrt64_square32 scratch
 uxth r2,r0
 lsrs r3,r0,#16
 mov r4,r2
 muls r4,r2
 muls r2,r3
 muls r3,r3
 lsls \scratch,r2,#17
 lsrs r2,#15
 adds r4,\scratch
 adcs r3,r2
.endm

.section .text.fo_sqrt_base,"ax",%progbits
.global fo_sqrt_base
.type fo_sqrt_base,%function
.thumb_func
fo_sqrt_base:
 lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
 bne .Lfo_base_slow
 cmp r3,#0
 bne .Lfo_base_normal
.Lfo_base_slow:
 push {r4,lr}
 bl fo_sqrt_base_slow
 pop {r4,pc}
.Lfo_base_normal:
 push {r4-r7,lr}
 // N=m*2^62, 1 <= m < 4. Preserve its low/high words and exponent.
 lsrs r6,r3,#1
 bcc 2f
 // The odd biased exponent already supplies the hidden bit.
 lsls r5,r1,#11
 lsrs r5,#1
 lsrs r4,r0,#22
 orrs r5,r4
 lsls r4,r0,#10
 b 1f
2:
 lsls r5,r1,#11
 movs r4,#1
 lsls r4,#31
 orrs r5,r4
 lsrs r4,r0,#21
 orrs r5,r4
 lsls r4,r0,#11
1:
 ldr r6,=1021
 adds r6,r3
 lsrs r6,#1
 lsls r6,#20
 // LR is available throughout this leaf path; keep N.low there.
 mov lr,r4
 // Both polynomials preserve N.high in R5 and the exponent in R6.
 // Parity + eight leading fraction bits select the midpoint.
 lsls r7,r1,#11
 lsrs r7,#23
 lsls r2,r1,#20
 lsrs r3,r0,#12
 orrs r2,r3
 movs r3,#1
 lsls r3,#31
 eors r2,r3
 asrs r2,#11
 adds r2,#1
 asrs r2,#1
 // Four packed words per row. The larger seed bounds still permit
 // one exact correction after Newton; the table occupies only 8 KiB.
 lsls r7,#4
 adr r4,.Lfo_base_coefficients
 adds r7,r4
 ldmia r7!,{r0,r1}
 asrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 lsrs r1,#9
 sqrt64_polynomial
 // A certified one-unit bias in the last cell keeps R within a word.
 mov r12,r0                   // R ~= sqrt(m)*2^31
 ldmia r7!,{r0,r1}
 lsrs r3,r1,#21
 lsls r3,#3
 lsls r1,#11
 asrs r1,#9
 sqrt64_polynomial
 mov r7,r0                    // V ~= 2^31/sqrt(m)
 mov r0,r12
 sqrt64_square32 r1
 mov r0,lr
 mov r2,r5
 subs r0,r4
 sbcs r2,r3
 // The signed residual fits 37 bits. Dropping six low bits contributes
 // less than 63*(2^31+13)/2^42 to the Q52 root error.
 lsrs r0,#6
 lsls r2,#26
 orrs r0,r2
 // The three partial products undershoot the real high product by <3.
 // Adding nine and shifting four places bounds the error below 5/8.
 asrs r4,r0,#16
 uxth r5,r0
 lsrs r3,r7,#16
 uxth r7,r7
 muls r5,r3
 lsrs r5,#16
 muls r7,r4
 asrs r7,#16
 muls r4,r3
 adds r4,r5
 adds r4,r7
 adds r4,#9
 asrs r2,r4,#4
 mov r0,r12
 lsrs r1,r0,#11
 lsls r0,#21
 asrs r3,r2,#31
 adds r0,r2
 adcs r1,r3
 // Certified polynomial errors (<11 root / <13 inverse Q31 units)
 // bound q's error below one unit. A single exact correction suffices.
 // Its signed 106-bit residual fits 64 bits; only the low square is needed.
 sqrt64_square32 r7
 mov r5,r0
 muls r5,r1
 lsls r5,#1
 adds r3,r5
 mov r7,lr
 lsls r7,#10
 movs r5,#0
 subs r5,r4
 sbcs r7,r3                   // R7:R5 = radicand-q*q
 bmi .Lfo_base_negative_residual
 cmp r7,r1
 blo .Lfo_base_pack
 bhi .Lfo_base_increment
 cmp r5,r0
 bls .Lfo_base_pack
.Lfo_base_increment:
 movs r2,#0
 adds r0,#1
 adcs r1,r2
 b .Lfo_base_pack
.Lfo_base_negative_residual:
 adds r5,r0
 adcs r7,r1
 bmi .Lfo_base_decrement
 bne .Lfo_base_pack
 cmp r5,#0
 bne .Lfo_base_pack
.Lfo_base_decrement:
 movs r2,#0
 subs r0,#1
 sbcs r1,r2
.Lfo_base_pack:
 adds r1,r6
 pop {r4-r7,pc}
.ltorg
.align 5
.Lfo_base_coefficients:
#include "baseline_sqrt_table.inc"
.size fo_sqrt_base,.-fo_sqrt_base
.section .text.fo_sqrt_new_cpu,"ax",%progbits
.global fo_sqrt_new_cpu
.type fo_sqrt_new_cpu,%function
.thumb_func
fo_sqrt_new_cpu:
 lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
 bne .Lfo_new_cpu_slow
 cmp r3,#0
 bne .Lfo_new_cpu_normal
.Lfo_new_cpu_slow:
 push {r4,lr}
 bl fo_sqrt_new_cpu_slow
 pop {r4,pc}
.Lfo_new_cpu_normal:
 push {r4-r7,lr}
 // N=m*2^62, 1 <= m < 4. Preserve its low/high words and exponent.
 lsrs r6,r3,#1
 bcc 2f
 // The odd biased exponent already supplies the hidden bit.
 lsls r5,r1,#11
 lsrs r5,#1
 lsrs r4,r0,#22
 orrs r5,r4
 lsls r4,r0,#10
 b 1f
2:
 lsls r5,r1,#11
 movs r4,#1
 lsls r4,#31
 orrs r5,r4
 lsrs r4,r0,#21
 orrs r5,r4
 lsls r4,r0,#11
1:
 ldr r6,=1021
 adds r6,r3
 lsrs r6,#1
 lsls r6,#20
 // LR is available throughout this leaf path; keep N.low there.
 sub sp,#4
 str r4,[sp]
 // The complete original correction and rounding tail follows this seed.
 adds r2,r3,#1
 movs r3,#1
 ands r2,r3
 movs r3,#0
 lsls r1,#12
 lsrs r1,#12
 movs r7,#1
 lsls r7,#20
 orrs r1,r7
 bl fo_sqrt_seed_cpu
 mov r7,r1
 mov r12,r0
 ldr r2,[sp]
 mov lr,r2
 add sp,#4
 mov r0,r12
 sqrt64_square32 r1
 mov r0,lr
 mov r2,r5
 subs r0,r4
 sbcs r2,r3
 // The signed residual fits 37 bits. Dropping six low bits contributes
 // less than 63*(2^31+13)/2^42 to the Q52 root error.
 lsrs r0,#6
 lsls r2,#26
 orrs r0,r2
 // The three partial products undershoot the real high product by <3.
 // Adding nine and shifting four places bounds the error below 5/8.
 asrs r4,r0,#16
 uxth r5,r0
 lsrs r3,r7,#16
 uxth r7,r7
 muls r5,r3
 lsrs r5,#16
 muls r7,r4
 asrs r7,#16
 muls r4,r3
 adds r4,r5
 adds r4,r7
 adds r4,#9
 asrs r2,r4,#4
 mov r0,r12
 lsrs r1,r0,#11
 lsls r0,#21
 asrs r3,r2,#31
 adds r0,r2
 adcs r1,r3
 // Certified polynomial errors (<11 root / <13 inverse Q31 units)
 // bound q's error below one unit. A single exact correction suffices.
 // Its signed 106-bit residual fits 64 bits; only the low square is needed.
 sqrt64_square32 r7
 mov r5,r0
 muls r5,r1
 lsls r5,#1
 adds r3,r5
 mov r7,lr
 lsls r7,#10
 movs r5,#0
 subs r5,r4
 sbcs r7,r3                   // R7:R5 = radicand-q*q
 bmi .Lfo_new_cpu_negative_residual
 cmp r7,r1
 blo .Lfo_new_cpu_pack
 bhi .Lfo_new_cpu_increment
 cmp r5,r0
 bls .Lfo_new_cpu_pack
.Lfo_new_cpu_increment:
 movs r2,#0
 adds r0,#1
 adcs r1,r2
 b .Lfo_new_cpu_pack
.Lfo_new_cpu_negative_residual:
 adds r5,r0
 adcs r7,r1
 bmi .Lfo_new_cpu_decrement
 bne .Lfo_new_cpu_pack
 cmp r5,#0
 bne .Lfo_new_cpu_pack
.Lfo_new_cpu_decrement:
 movs r2,#0
 subs r0,#1
 sbcs r1,r2
.Lfo_new_cpu_pack:
 adds r1,r6
 pop {r4-r7,pc}
.ltorg
.size fo_sqrt_new_cpu,.-fo_sqrt_new_cpu
.section .text.fo_sqrt_new_interp,"ax",%progbits
.global fo_sqrt_new_interp
.type fo_sqrt_new_interp,%function
.thumb_func
fo_sqrt_new_interp:
 lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
 bne .Lfo_new_interp_slow
 cmp r3,#0
 bne .Lfo_new_interp_normal
.Lfo_new_interp_slow:
 push {r4,lr}
 bl fo_sqrt_new_interp_slow
 pop {r4,pc}
.Lfo_new_interp_normal:
 push {r4-r7,lr}
 // N=m*2^62, 1 <= m < 4. Preserve its low/high words and exponent.
 lsrs r6,r3,#1
 bcc 2f
 // The odd biased exponent already supplies the hidden bit.
 lsls r5,r1,#11
 lsrs r5,#1
 lsrs r4,r0,#22
 orrs r5,r4
 lsls r4,r0,#10
 b 1f
2:
 lsls r5,r1,#11
 movs r4,#1
 lsls r4,#31
 orrs r5,r4
 lsrs r4,r0,#21
 orrs r5,r4
 lsls r4,r0,#11
1:
 ldr r6,=1021
 adds r6,r3
 lsrs r6,#1
 lsls r6,#20
 // LR is available throughout this leaf path; keep N.low there.
 sub sp,#4
 str r4,[sp]
 // The complete original correction and rounding tail follows this seed.
 adds r2,r3,#1
 movs r3,#1
 ands r2,r3
 movs r3,#0
 lsls r1,#12
 lsrs r1,#12
 movs r7,#1
 lsls r7,#20
 orrs r1,r7
 bl fo_sqrt_seed_interp
 mov r7,r1
 mov r12,r0
 ldr r2,[sp]
 mov lr,r2
 add sp,#4
 mov r0,r12
 sqrt64_square32 r1
 mov r0,lr
 mov r2,r5
 subs r0,r4
 sbcs r2,r3
 // The signed residual fits 37 bits. Dropping six low bits contributes
 // less than 63*(2^31+13)/2^42 to the Q52 root error.
 lsrs r0,#6
 lsls r2,#26
 orrs r0,r2
 // The three partial products undershoot the real high product by <3.
 // Adding nine and shifting four places bounds the error below 5/8.
 asrs r4,r0,#16
 uxth r5,r0
 lsrs r3,r7,#16
 uxth r7,r7
 muls r5,r3
 lsrs r5,#16
 muls r7,r4
 asrs r7,#16
 muls r4,r3
 adds r4,r5
 adds r4,r7
 adds r4,#9
 asrs r2,r4,#4
 mov r0,r12
 lsrs r1,r0,#11
 lsls r0,#21
 asrs r3,r2,#31
 adds r0,r2
 adcs r1,r3
 // Certified polynomial errors (<11 root / <13 inverse Q31 units)
 // bound q's error below one unit. A single exact correction suffices.
 // Its signed 106-bit residual fits 64 bits; only the low square is needed.
 sqrt64_square32 r7
 mov r5,r0
 muls r5,r1
 lsls r5,#1
 adds r3,r5
 mov r7,lr
 lsls r7,#10
 movs r5,#0
 subs r5,r4
 sbcs r7,r3                   // R7:R5 = radicand-q*q
 bmi .Lfo_new_interp_negative_residual
 cmp r7,r1
 blo .Lfo_new_interp_pack
 bhi .Lfo_new_interp_increment
 cmp r5,r0
 bls .Lfo_new_interp_pack
.Lfo_new_interp_increment:
 movs r2,#0
 adds r0,#1
 adcs r1,r2
 b .Lfo_new_interp_pack
.Lfo_new_interp_negative_residual:
 adds r5,r0
 adcs r7,r1
 bmi .Lfo_new_interp_decrement
 bne .Lfo_new_interp_pack
 cmp r5,#0
 bne .Lfo_new_interp_pack
.Lfo_new_interp_decrement:
 movs r2,#0
 subs r0,#1
 sbcs r1,r2
.Lfo_new_interp_pack:
 adds r1,r6
 pop {r4-r7,pc}
.ltorg
.size fo_sqrt_new_interp,.-fo_sqrt_new_interp
.section .text.fo_sqrt_skip_refine,"ax",%progbits
.global fo_sqrt_skip_refine
.type fo_sqrt_skip_refine,%function
.thumb_func
fo_sqrt_skip_refine:
 lsrs r3,r1,#20
 adds r2,r3,#1
 lsrs r2,#11
 bne .Lfo_skip_refine_slow
 cmp r3,#0
 bne .Lfo_skip_refine_normal
.Lfo_skip_refine_slow:
 push {r4,lr}
 bl fo_sqrt_skip_refine_slow
 pop {r4,pc}
.Lfo_skip_refine_normal:
 push {r4-r7,lr}
 // N=m*2^62, 1 <= m < 4. Preserve its low/high words and exponent.
 lsrs r6,r3,#1
 bcc 2f
 // The odd biased exponent already supplies the hidden bit.
 lsls r5,r1,#11
 lsrs r5,#1
 lsrs r4,r0,#22
 orrs r5,r4
 lsls r4,r0,#10
 b 1f
2:
 lsls r5,r1,#11
 movs r4,#1
 lsls r4,#31
 orrs r5,r4
 lsrs r4,r0,#21
 orrs r5,r4
 lsls r4,r0,#11
1:
 ldr r6,=1021
 adds r6,r3
 lsrs r6,#1
 lsls r6,#20
 // LR is available throughout this leaf path; keep N.low there.
 sub sp,#4
 str r4,[sp]
 // The complete original correction and rounding tail follows this seed.
 adds r2,r3,#1
 movs r3,#1
 ands r2,r3
 movs r3,#0
 lsls r1,#12
 lsrs r1,#12
 movs r7,#1
 lsls r7,#20
 orrs r1,r7
 bl fo_sqrt_seed_cpu
 mov r7,r1
 mov r12,r0
 ldr r2,[sp]
 mov lr,r2
 add sp,#4
 mov r0,r12
 lsrs r1,r0,#11
 lsls r0,#21
 sqrt64_square32 r7
 mov r5,r0
 muls r5,r1
 lsls r5,#1
 adds r3,r5
 mov r7,lr
 lsls r7,#10
 movs r5,#0
 subs r5,r4
 sbcs r7,r3                   // R7:R5 = radicand-q*q
 bmi .Lfo_skip_refine_negative_residual
 cmp r7,r1
 blo .Lfo_skip_refine_pack
 bhi .Lfo_skip_refine_increment
 cmp r5,r0
 bls .Lfo_skip_refine_pack
.Lfo_skip_refine_increment:
 movs r2,#0
 adds r0,#1
 adcs r1,r2
 b .Lfo_skip_refine_pack
.Lfo_skip_refine_negative_residual:
 adds r5,r0
 adcs r7,r1
 bmi .Lfo_skip_refine_decrement
 bne .Lfo_skip_refine_pack
 cmp r5,#0
 bne .Lfo_skip_refine_pack
.Lfo_skip_refine_decrement:
 movs r2,#0
 subs r0,#1
 sbcs r1,r2
.Lfo_skip_refine_pack:
 adds r1,r6
 pop {r4-r7,pc}
.ltorg
.size fo_sqrt_skip_refine,.-fo_sqrt_skip_refine
