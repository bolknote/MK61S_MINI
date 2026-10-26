#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
// Exact32x32 product, with a possible carry in the16-bit cross sum.
.macro ir_mul32 x,y,lo,hi,t0,t1,t2,t3,t4
 uxth \t0,\x
 uxth \t1,\y
 muls \t0,\t1
 lsrs \t2,\x,#16
 muls \t1,\t2
 lsrs \t4,\y,#16
 muls \t2,\t4
 uxth \t3,\x
 muls \t3,\t4
 adds \t1,\t3
 bcc .Lir_mul_fit\@
 movs \t3,#1
 lsls \t3,#16
 adds \t2,\t3
.Lir_mul_fit\@:
 lsls \lo,\t1,#16
 lsrs \hi,\t1,#16
 adds \lo,\t0
 adcs \hi,\t2
.endm
.macro ir_square32 x,lo,hi,t0,t1,t2
 uxth \t0,\x
 muls \t0,\t0
 uxth \t1,\x
 lsrs \t2,\x,#16
 muls \t1,\t2
 muls \t2,\t2
 lsls \lo,\t1,#17
 lsrs \hi,\t1,#15
 adds \lo,\t0
 adcs \hi,\t2
.endm
.macro ir_center_quotient
 mov r12,r0
 mov r5,r6
 uxth r6,r7
 lsrs r2,r7,#16
 muls r6,r2
 muls r2,r2
 lsrs r6,#15
 adds r2,r6
 movs r6,#9
 subs r6,r6,r3
 lsrs r2,r6
 ir_mul32 r0,r2,r0,r1,r3,r6,r4,r0,r2
 mov r4,r12
 mov r0,r1
 muls r0,r5
 subs r0,r4,r0
 cmp r0,r5
 blo .Lir_div_done\@
 subs r0,r0,r5
 adds r1,#1
 cmp r0,r5
 blo .Lir_div_done\@
 adds r1,#1
.Lir_div_done\@:
 mov r0,r1
.endm
.section .m0_pow_dispatch_extension,"ax",%progbits
.align 2
.global mk61_m0_pow_rsqrt_fast
.hidden mk61_m0_pow_rsqrt_fast
.type mk61_m0_pow_rsqrt_fast,%function
.thumb_func
// Positive normal binary64 only. The unchanged entry keeps cold IEEE and
// subnormal inputs in the old dispatcher. Integer point matches pow_rsqrt.
mk61_m0_pow_rsqrt_fast:
 push {r4-r7,lr}
 sub sp,#44
 str r0,[sp,#0]
 // Original xhigh was used only by the impossible compare==2 fallback.
 lsrs r2,r1,#20
 ldr r4,=3066
 subs r4,r4,r2
 lsrs r4,#1
 lsls r4,#20
 str r4,[sp,#12]
 adds r2,#1
 movs r3,#1
 ands r2,r3
 str r2,[sp,#16]
 lsls r4,r1,#12
 lsrs r4,#12
 movs r5,#1
 lsls r5,#20
 orrs r4,r5
 str r4,[sp,#4]
 lsrs r6,r4,#12
 uxtb r6,r6
 lsls r2,#8
 orrs r2,r6
 lsls r2,#2
 ldr r3,=factor_rsqrt_seeds
 ldr r7,[r3,r2]
 lsls r6,#1
 ldr r3,=513
 adds r6,r3
 lsls r5,r6,#11
 ldr r0,[sp,#0]
 subs r1,r4,r5
 movs r2,#0
 sbcs r2,r2
 str r2,[sp,#20]
 eors r0,r2
 eors r1,r2
 subs r0,r0,r2
 sbcs r1,r2
 mov r3,r0
 orrs r3,r1
 beq .Lir_t_ready
 subs r0,#1
 movs r3,#0
 sbcs r1,r3
 lsrs r0,#11
 lsls r1,#21
 orrs r0,r1
 beq .Lir_t_ready
 // The quotient now preserves R7 directly, avoiding a seed store/load.
 ldr r3,[sp,#16]
 ir_center_quotient
.global mk61_m0_pow_center_quotient_end
.hidden mk61_m0_pow_center_quotient_end
mk61_m0_pow_center_quotient_end:
.Lir_t_ready:
 // The exact old quadratic/cubic32-bit seed correction.
 ir_square32 r0,r1,r2,r3,r4,r5
 movs r4,#3
 muls r4,r2
 adds r4,#4
 lsrs r4,#3
 lsls r4,#1
 lsrs r3,r0,#16
 muls r2,r3
 lsrs r2,#16
 movs r3,#5
 muls r2,r3
 adds r2,#8
 lsrs r2,#4
 lsls r2,#1
 adds r0,r2
 ldr r1,[sp,#20]
 cmp r1,#0
 beq .Lir_mag_above
 adds r0,r4
 b .Lir_mag_ready
.Lir_mag_above:
 subs r0,r0,r4
.Lir_mag_ready:
 mov r1,r7
 ir_mul32 r0,r1,r0,r1,r2,r3,r4,r0,r1
 adds r1,#1
 lsrs r1,#1
 ldr r2,[sp,#20]
 cmp r2,#0
 beq .Lir_seed_subtract
 adds r7,r7,r1
 bcc .Lir_seed_ready
 movs r7,#0
 mvns r7,r7
 b .Lir_seed_ready
.Lir_seed_subtract:
 subs r7,r7,r1
.Lir_seed_ready:
 str r7,[sp,#24]
 // A=m<<(10+parity), retaining both complete32-bit words.
 ldr r0,[sp,#0]
 ldr r1,[sp,#4]
 ldr r2,[sp,#16]
 adds r2,#10
 movs r3,#32
 subs r3,r3,r2
 mov r4,r0
 lsrs r4,r3
 lsls r1,r2
 orrs r1,r4
 lsls r0,r2
 str r0,[sp,#28]
 str r1,[sp,#32]
 mov r0,r7
 ir_square32 r0,r4,r5,r1,r2,r3
 // Old exp_high_product: Ah*Bh+high32(Al*Bh)+high32(Ah*Bl).
 ldr r0,[sp,#28]
 mov r1,r5
 ir_mul32 r0,r1,r0,r1,r2,r3,r6,r0,r1
 mov r7,r1
 ldr r0,[sp,#32]
 mov r1,r4
 ir_mul32 r0,r1,r0,r1,r2,r3,r6,r0,r1
 adds r7,r1
 movs r6,#0
 adcs r6,r6
 ldr r0,[sp,#32]
 mov r1,r5
 ir_mul32 r0,r1,r0,r1,r2,r3,r4,r0,r1
 adds r0,r7
 adcs r1,r6
 movs r2,#0
 ldr r3,=0xc0000000
 subs r0,r2,r0
 sbcs r3,r1
 str r3,[sp,#28]
 // SP20's old sign is dead; retain Flow for the local rounding bound.
 // Moving the removed xhigh store here keeps ordinary instruction counts.
 str r0,[sp,#20]
 // q=floor(factor*seed/2^32), exact same two-term64x32 product.
 // R6's cross-product carry is dead after ADCS above. Keep seed once.
 ldr r6,[sp,#24]
 ir_mul32 r0,r6,r0,r1,r2,r3,r4,r0,r1
 mov r7,r1
 ldr r0,[sp,#28]
 // These two common factor words have exact shift/subtract products.
 // Every other word still uses the complete32x32 multiplication.
 ldr r2,=0x7fffffff
 cmp r0,r2
 beq .Lir_factor_below
 adds r2,#1
 cmp r0,r2
 beq .Lir_factor_equal
 ir_mul32 r0,r6,r0,r1,r2,r3,r4,r0,r1
 b .Lir_factor_product
.Lir_factor_below:
 lsls r0,r6,#31
 lsrs r2,r6,#1
 subs r0,r0,r6
 movs r1,#0
 sbcs r2,r1
 mov r1,r2
 b .Lir_factor_product
.Lir_factor_equal:
 lsls r0,r6,#31
 lsrs r1,r6,#1
.Lir_factor_product:
 adds r0,r7
 movs r2,#0
 adcs r1,r2
.global mk61_m0_pow_rsqrt_point
.hidden mk61_m0_pow_rsqrt_point
mk61_m0_pow_rsqrt_point:
 // Exact rational certificate: seed error<25/8; Newton down error
 // <15.649 and up error<3 in this Q63 coordinate. Only integer tails
 // [497,514] need the original exact midpoint comparison.
 mov r2,r0
 lsls r2,#22
 lsrs r2,#22
 subs r2,#255
 subs r2,#242
 cmp r2,#17
 bls .Lir_boundary
 // An accepted interval excludes an exact midpoint, so half-up is RNE.
.Lir_point_round:
 ldr r2,=512
 adds r0,r2
 movs r2,#0
 adcs r1,r2
 lsls r2,r1,#22
 lsrs r0,#10
 orrs r0,r2
 lsrs r1,#10
 ldr r2,[sp,#12]
 adds r1,r2
 add sp,#44
 pop {r4-r7,pc}
.Lir_boundary:
 // R2 is the retained tail minus497, already in[0,17]. For either
 // central factor word, the strict local bound is q-3<Y<q+4.
 // Tails497..508 therefore round down without the 161-bit comparison.
.global mk61_m0_pow_rsqrt_local_guard_begin
.hidden mk61_m0_pow_rsqrt_local_guard_begin
mk61_m0_pow_rsqrt_local_guard_begin:
 cmp r2,#11
 bhi .Lir_local_q8
 ldr r2,[sp,#28]
 ldr r3,=0x7fffffff
 subs r2,r2,r3
 cmp r2,#1
 bls .Lir_point_round
.global mk61_m0_pow_rsqrt_local_guard_end
.hidden mk61_m0_pow_rsqrt_local_guard_end
mk61_m0_pow_rsqrt_local_guard_end:
.Lir_exact_boundary:
 lsls r2,r1,#22
 lsrs r0,#10
 orrs r0,r2
 lsrs r1,#10
 ldr r2,=0x3fd00000
 adds r1,r2
 str r0,[sp,#36]
 str r1,[sp,#40]
 ldr r0,[sp,#0]
 str r0,[sp,#24]
 ldr r1,[sp,#4]
 ldr r2,[sp,#16]
 ldr r3,[sp,#36]
 str r3,[sp,#0]
 ldr r3,[sp,#40]
 str r3,[sp,#4]
 bl mk61_m0_pow_rsqrt_boundary
 // lower=0x3fd...+(any uint64 q>>10) has exponent-2..1;
 // parity0or1 gives target bit155..162. Return2 is unreachable.
 cmp r0,#0
 bmi .Lir_increment_lower
 bne .Lir_boundary_pack
 ldr r1,[sp,#36]
 lsls r1,#31
 bpl .Lir_boundary_pack
.Lir_increment_lower:
 ldr r0,[sp,#36]
 ldr r1,[sp,#40]
 adds r0,#1
 movs r2,#0
 adcs r1,r2
 b .Lir_boundary_scale
.Lir_boundary_pack:
 ldr r0,[sp,#36]
 ldr r1,[sp,#40]
.Lir_boundary_scale:
 ldr r2,[sp,#12]
 ldr r3,=0x3fd00000
 subs r2,r2,r3
 adds r1,r2
 add sp,#44
 pop {r4-r7,pc}
.Lir_local_q8:
 // Preserve the existing coarse fast exit. The additional helper runs
 // only for its remaining upper-tail ambiguous cases and central words.
 ldr r2,[sp,#28]
 ldr r3,=0x7fffffff
 subs r2,r2,r3
 cmp r2,#1
 bhi .Lir_exact_boundary
 str r0,[sp,#36]
 str r1,[sp,#40]
 // R5 is still high32(seed^2), live unchanged from ir_square32.
 str r5,[sp,#8]
.global mk61_m0_pow_rsqrt_q8_frame_ready
.hidden mk61_m0_pow_rsqrt_q8_frame_ready
mk61_m0_pow_rsqrt_q8_frame_ready:
 mov r0,sp
 // CMP r2,#1 above leaves C=0 for Fhigh7fffffff, C=1 for80000000.
 // BHI, three STR, MOV sp and BL preserve C until the private entry SBC.
 bl mk61_m0_pow_rsqrt_local_q8_native
 mov r2,r0
 orrs r2,r1
 beq .Lir_local_q8_decline
 add sp,#44
 pop {r4-r7,pc}
.Lir_local_q8_decline:
 ldr r0,[sp,#36]
 ldr r1,[sp,#40]
 b .Lir_exact_boundary
.ltorg
.size mk61_m0_pow_rsqrt_fast,.-mk61_m0_pow_rsqrt_fast


#endif
