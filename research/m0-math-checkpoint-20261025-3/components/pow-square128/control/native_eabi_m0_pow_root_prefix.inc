/* Project-owned bounded Horner pow kernels; frozen GNU Thumb schedule.
 * Exact-base products between roots; strict certification retains refinement.
 * No coefficient or global RAM additions. Clang is an optional reference only. */
	.syntax	unified
	.eabi_attribute	67, "2.09"	@ Tag_conformance
	.cpu	cortex-m0plus
	.eabi_attribute	6, 12	@ Tag_CPU_arch
	.eabi_attribute	7, 77	@ Tag_CPU_arch_profile
	.eabi_attribute	8, 0	@ Tag_ARM_ISA_use
	.eabi_attribute	9, 1	@ Tag_THUMB_ISA_use
	.eabi_attribute	34, 0	@ Tag_CPU_unaligned_access
	.eabi_attribute	17, 1	@ Tag_ABI_PCS_GOT_use
	.eabi_attribute	20, 1	@ Tag_ABI_FP_denormal
	.eabi_attribute	21, 0	@ Tag_ABI_FP_exceptions
	.eabi_attribute	23, 3	@ Tag_ABI_FP_number_model
	.eabi_attribute	24, 1	@ Tag_ABI_align_needed
	.eabi_attribute	25, 1	@ Tag_ABI_align_preserved
	.eabi_attribute	38, 1	@ Tag_ABI_FP_16bit_format
	.eabi_attribute	18, 4	@ Tag_ABI_PCS_wchar_t
	.eabi_attribute	14, 0	@ Tag_ABI_PCS_R9_use
	.file	"kernels.cpp"
	.section	.m0_pow_root_prefix,"ax",%progbits
	.globl	pow_integer128_approx_high64    @ -- Begin function pow_integer128_approx_high64
	.p2align	1
	.type	pow_integer128_approx_high64,%function
	.code	16
	.thumb_func
pow_integer128_approx_high64:           @ @pow_integer128_approx_high64
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	lsrs	r5, r2, #16
	lsrs	r4, r1, #16
	mov	r6, r5
	muls	r6, r4, r6
	uxth	r1, r1
	muls	r5, r1, r5
	lsrs	r5, r5, #16
	adds	r5, r5, r6
	uxth	r2, r2
	muls	r2, r4, r2
	lsrs	r2, r2, #16
	adds	r5, r5, r2
	lsrs	r6, r0, #16
	lsrs	r2, r3, #16
	mov	r7, r6
	muls	r7, r2, r7
	uxth	r0, r0
	muls	r0, r2, r0
	lsrs	r0, r0, #16
	adds	r7, r0, r7
	uxth	r0, r3
	muls	r6, r0, r6
	lsrs	r3, r6, #16
	adds	r6, r7, r3
	movs	r3, #0
	adds	r5, r6, r5
	adcs	r3, r3
	mov	r6, r4
	muls	r6, r0, r6
	muls	r0, r1, r0
	lsrs	r7, r0, #16
	adds	r6, r7, r6
	lsrs	r7, r6, #16
	muls	r4, r2, r4
	adds	r4, r7, r4
	uxth	r6, r6
	muls	r1, r2, r1
	adds	r2, r6, r1
	lsrs	r1, r2, #16
	adds	r1, r4, r1
	lsls	r2, r2, #16
	uxth	r0, r0
	adds	r0, r2, r0
	adds	r0, r5, r0
	adcs	r1, r3
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end0:
	.size	pow_integer128_approx_high64, .Lpow_horner_func_end0-pow_integer128_approx_high64
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	pow_integer128_base             @ -- Begin function pow_integer128_base
	.p2align	1
	.type	pow_integer128_base,%function
	.code	16
	.thumb_func
pow_integer128_base:                    @ @pow_integer128_base
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#52
	sub	sp, #52
	str	r1, [sp, #44]                   @ 4-byte Spill
	str	r0, [sp, #48]                   @ 4-byte Spill
	ldr	r4, [r0]
	lsrs	r5, r4, #16
	ldr	r2, [r1]
	uxth	r1, r2
	mov	r3, r5
	str	r5, [sp, #32]                   @ 4-byte Spill
	muls	r3, r1, r3
	uxth	r4, r4
	mov	r0, r4
	str	r4, [sp, #28]                   @ 4-byte Spill
	muls	r0, r1, r0
	str	r0, [sp, #40]                   @ 4-byte Spill
	lsrs	r0, r0, #16
	adds	r3, r0, r3
	lsrs	r7, r3, #16
	str	r2, [sp, #8]                    @ 4-byte Spill
	lsrs	r0, r2, #16
	muls	r5, r0, r5
	adds	r6, r7, r5
	uxth	r3, r3
	muls	r4, r0, r4
	adds	r2, r3, r4
	str	r2, [sp, #36]                   @ 4-byte Spill
	lsrs	r3, r2, #16
	adds	r6, r6, r3
	str	r6, [sp, #16]                   @ 4-byte Spill
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	ldr	r3, [r2, #4]
	lsrs	r2, r3, #16
	mov	r4, r2
	muls	r4, r1, r4
	uxth	r5, r3
	muls	r1, r5, r1
	lsrs	r3, r1, #16
	adds	r3, r3, r4
	lsrs	r4, r3, #16
	mov	r7, r2
	muls	r7, r0, r7
	adds	r4, r4, r7
	uxth	r3, r3
	muls	r0, r5, r0
	adds	r0, r3, r0
	lsrs	r7, r0, #16
	lsls	r0, r0, #16
	uxth	r1, r1
	adds	r0, r0, r1
	str	r0, [sp, #20]                   @ 4-byte Spill
	adds	r0, r6, r0
	mov	r0, r4
	adcs	r0, r7
	str	r0, [sp, #24]                   @ 4-byte Spill
	adds	r0, r4, r7
	str	r0, [sp, #12]                   @ 4-byte Spill
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	ldr	r6, [r0, #4]
	uxth	r4, r6
	mov	r0, r2
	muls	r0, r4, r0
	mov	r7, r5
	muls	r7, r4, r7
	lsrs	r3, r7, #16
	adds	r3, r3, r0
	lsrs	r1, r3, #16
	str	r6, [sp, #4]                    @ 4-byte Spill
	lsrs	r6, r6, #16
	muls	r2, r6, r2
	adds	r1, r1, r2
	uxth	r2, r3
	muls	r5, r6, r5
	adds	r2, r2, r5
	lsrs	r5, r2, #16
	lsls	r2, r2, #16
	uxth	r3, r7
	adds	r7, r2, r3
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r2, [sp, #16]                   @ 4-byte Reload
	adds	r0, r2, r0
	str	r0, [sp, #20]                   @ 4-byte Spill
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	adcs	r0, r7
	adcs	r5, r1
	mov	r3, r5
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	mov	r5, r1
	muls	r5, r4, r5
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	muls	r4, r0, r4
	lsrs	r2, r4, #16
	adds	r5, r2, r5
	lsrs	r2, r5, #16
	muls	r1, r6, r1
	adds	r2, r2, r1
	uxth	r1, r5
	mov	r5, r3
	muls	r0, r6, r0
	adds	r0, r1, r0
	lsrs	r1, r0, #16
	lsls	r0, r0, #16
	uxth	r4, r4
	adds	r0, r0, r4
	ldr	r3, [sp, #20]                   @ 4-byte Reload
	adds	r0, r0, r3
	str	r0, [sp, #32]                   @ 4-byte Spill
	adcs	r1, r2
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	adds	r0, r7, r0
	movs	r2, #0
	adds	r3, r0, r1
	str	r2, [sp, #28]                   @ 4-byte Spill
	adcs	r5, r2
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	lsls	r0, r0, #16
	ldr	r1, [sp, #40]                   @ 4-byte Reload
	uxth	r1, r1
	adds	r7, r0, r1
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	ldr	r0, [r2, #16]
	ldr	r1, [sp, #44]                   @ 4-byte Reload
	ldr	r1, [r1, #16]
	adds	r4, r1, r0
	ldr	r1, [r2, #12]
	ldr	r0, [r2, #8]
	mov	r6, r0
	orrs	r6, r1
	beq	.Lpow_horner_BB1_2
@ %bb.1:
	ldr	r2, [sp, #8]                    @ 4-byte Reload
	str	r4, [sp, #36]                   @ 4-byte Spill
	mov	r4, r3
	ldr	r3, [sp, #4]                    @ 4-byte Reload
	bl	pow_integer128_approx_high64
	adds	r7, r0, r7
	str	r7, [sp, #40]                   @ 4-byte Spill
	ldr	r0, [sp, #32]                   @ 4-byte Reload
	adcs	r1, r0
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	adcs	r4, r0
	str	r4, [sp, #44]                   @ 4-byte Spill
	ldr	r4, [sp, #36]                   @ 4-byte Reload
	adcs	r5, r0
	b	.Lpow_horner_BB1_3
.Lpow_horner_BB1_2:
	str	r7, [sp, #40]                   @ 4-byte Spill
	str	r3, [sp, #44]                   @ 4-byte Spill
	ldr	r1, [sp, #32]                   @ 4-byte Reload
.Lpow_horner_BB1_3:
	ldr	r7, [sp, #48]                   @ 4-byte Reload
	str	r4, [r7, #16]
	ldr	r0, [r7, #20]
	.inst.n	0x1e43 @ subs	r3, r0, #1
	mov	r2, r0
	sbcs	r2, r3
	cmp	r6, #0
	beq	.Lpow_horner_BB1_5
@ %bb.4:
	movs	r2, #8
.Lpow_horner_BB1_5:
	adds	r0, r2, r0
	cmp	r5, #0
	ldr	r6, [sp, #40]                   @ 4-byte Reload
	bmi	.Lpow_horner_BB1_7
@ %bb.6:
	lsrs	r2, r6, #31
	lsls	r3, r1, #1
	adds	r2, r3, r2
	ldr	r4, [sp, #44]                   @ 4-byte Reload
	lsrs	r3, r4, #31
	lsls	r5, r5, #1
	adds	r5, r5, r3
	lsls	r3, r4, #1
	lsrs	r1, r1, #31
	adds	r3, r3, r1
	lsls	r6, r6, #1
	lsls	r0, r0, #1
	mov	r1, r2
	b	.Lpow_horner_BB1_8
.Lpow_horner_BB1_7:
	.inst.n	0x1c62 @ adds	r2, r4, #1
	str	r2, [r7, #16]
	ldr	r3, [sp, #44]                   @ 4-byte Reload
.Lpow_horner_BB1_8:
	str	r6, [r7, #8]
	str	r3, [r7]
	str	r0, [r7, #20]
	str	r1, [r7, #12]
	str	r5, [r7, #4]
	add	sp, #52
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end1:
	.size	pow_integer128_base, .Lpow_horner_func_end1-pow_integer128_base
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	root64_boundary                 @ -- Begin function root64_boundary
	.p2align	2
	.type	root64_boundary,%function
	.code	16
	.thumb_func
root64_boundary:                        @ @root64_boundary
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#28
	sub	sp, #28
	mov	r1, r0
	ldr	r0, .Lpow_horner_CPI2_0
	.inst.n	0x1c54 @ adds	r4, r2, #1
	mov	r5, r3
	sbcs	r5, r0
	movs	r0, #0
	ldr	r6, .Lpow_horner_CPI2_1
	.inst.n	0x1e64 @ subs	r4, r4, #1
	adcs	r6, r5
	blo	.Lpow_horner_BB2_5
@ %bb.1:
	ldr	r5, [r1, #12]
	movs	r6, #1
	lsls	r4, r6, #20
	cmp	r5, r4
	bhi	.Lpow_horner_BB2_5
@ %bb.2:
	ldr	r0, [r1, #8]
	lsrs	r4, r3, #20
	adds	r4, r0, r4
	ldr	r7, .Lpow_horner_CPI2_3
	.inst.n	0x1cb8 @ adds	r0, r7, #2
	cmp	r4, r0
	mov	r0, r6
	bgt	.Lpow_horner_BB2_5
@ %bb.3:
	str	r5, [sp, #24]                   @ 4-byte Spill
	movs	r5, #0
	cmp	r4, r7
	bge	.Lpow_horner_BB2_6
@ %bb.4:
	mvns	r0, r5
.Lpow_horner_BB2_5:
	add	sp, #28
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_BB2_6:
	ldr	r0, .Lpow_horner_CPI2_2
	adds	r0, r4, r0
	str	r0, [sp, #8]                    @ 4-byte Spill
	lsrs	r0, r2, #21
	lsls	r3, r3, #11
	adds	r0, r3, r0
	str	r5, [sp, #12]                   @ 4-byte Spill
	uxth	r6, r0
	ldr	r0, [r1, #4]
	lsrs	r5, r0, #16
	str	r5, [sp, #20]                   @ 4-byte Spill
	mov	r4, r6
	muls	r4, r5, r4
	uxth	r0, r0
	str	r0, [sp, #16]                   @ 4-byte Spill
	mov	r5, r6
	muls	r5, r0, r5
	str	r5, [sp]                        @ 4-byte Spill
	lsrs	r0, r5, #16
	adds	r7, r0, r4
	lsrs	r0, r7, #16
	str	r0, [sp, #4]                    @ 4-byte Spill
	movs	r0, #1
	lsls	r4, r0, #15
	lsrs	r5, r3, #16
	orrs	r5, r4
	mov	r3, r5
	ldr	r4, [sp, #20]                   @ 4-byte Reload
	muls	r3, r4, r3
	ldr	r4, [sp, #4]                    @ 4-byte Reload
	adds	r3, r4, r3
	str	r3, [sp, #4]                    @ 4-byte Spill
	uxth	r7, r7
	mov	r4, r5
	ldr	r3, [sp, #16]                   @ 4-byte Reload
	muls	r4, r3, r4
	adds	r7, r7, r4
	lsrs	r4, r7, #16
	ldr	r3, [sp, #4]                    @ 4-byte Reload
	adds	r3, r3, r4
	str	r3, [sp, #4]                    @ 4-byte Spill
	ldr	r1, [r1]
	lsrs	r3, r1, #16
	mov	r4, r6
	muls	r4, r3, r4
	uxth	r1, r1
	muls	r6, r1, r6
	lsrs	r6, r6, #16
	adds	r4, r6, r4
	lsrs	r6, r4, #16
	muls	r3, r5, r3
	adds	r3, r6, r3
	uxth	r4, r4
	muls	r5, r1, r5
	adds	r1, r4, r5
	lsrs	r1, r1, #16
	adds	r1, r3, r1
	lsls	r3, r7, #16
	ldr	r4, [sp]                        @ 4-byte Reload
	uxth	r4, r4
	adds	r3, r3, r4
	adds	r3, r3, r1
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	adcs	r1, r1
	lsls	r4, r0, #10
	lsls	r2, r2, #11
	adds	r4, r2, r4
	uxth	r4, r4
	mov	r5, r4
	ldr	r7, [sp, #20]                   @ 4-byte Reload
	muls	r5, r7, r5
	ldr	r6, [sp, #16]                   @ 4-byte Reload
	muls	r4, r6, r4
	lsrs	r4, r4, #16
	adds	r4, r4, r5
	lsrs	r5, r4, #16
	lsrs	r2, r2, #16
	muls	r7, r2, r7
	adds	r5, r5, r7
	uxth	r4, r4
	muls	r2, r6, r2
	adds	r2, r4, r2
	lsrs	r2, r2, #16
	adds	r2, r5, r2
	ldr	r5, [sp, #8]                    @ 4-byte Reload
	adds	r2, r3, r2
	ldr	r3, [sp, #4]                    @ 4-byte Reload
	adcs	r1, r3
	ldr	r3, [sp, #24]                   @ 4-byte Reload
	.inst.n	0x1cdb @ adds	r3, r3, #3
	.inst.n	0x1cac @ adds	r4, r5, #2
	bne	.Lpow_horner_BB2_9
@ %bb.7:
	movs	r4, #0
	rsbs	r0, r3, #0
	mov	r3, r4
	sbcs	r3, r4
	subs	r0, r2, r0
	sbcs	r1, r3
	blo	.Lpow_horner_BB2_11
@ %bb.8:
	mov	r0, r4
	b	.Lpow_horner_BB2_12
.Lpow_horner_BB2_9:
	cmp	r5, #0
	beq	.Lpow_horner_BB2_14
@ %bb.10:
	lsls	r4, r0, #31
	b	.Lpow_horner_BB2_15
.Lpow_horner_BB2_11:
	movs	r0, #1
.Lpow_horner_BB2_12:
	cmp	r0, #0
	beq	.Lpow_horner_BB2_5
@ %bb.13:
	mvns	r0, r4
	b	.Lpow_horner_BB2_5
.Lpow_horner_BB2_14:
	lsls	r4, r0, #30
.Lpow_horner_BB2_15:
	cmp	r1, r4
	bhs	.Lpow_horner_BB2_18
@ %bb.16:
	rsbs	r0, r2, #0
	sbcs	r4, r1
	movs	r1, #0
	subs	r0, r3, r0
	mov	r0, r1
	sbcs	r0, r4
	blo	.Lpow_horner_BB2_20
@ %bb.17:
	mov	r0, r1
	b	.Lpow_horner_BB2_21
.Lpow_horner_BB2_18:
	subs	r1, r1, r4
	subs	r2, r3, r2
	ldr	r3, [sp, #12]                   @ 4-byte Reload
	mov	r2, r3
	sbcs	r2, r1
	bhs	.Lpow_horner_BB2_19
	b	.Lpow_horner_BB2_5
.Lpow_horner_BB2_19:
	mov	r0, r3
	b	.Lpow_horner_BB2_5
.Lpow_horner_BB2_20:
	movs	r0, #1
.Lpow_horner_BB2_21:
	cmp	r0, #0
	bne	.Lpow_horner_BB2_22
	b	.Lpow_horner_BB2_5
.Lpow_horner_BB2_22:
	mvns	r0, r1
	b	.Lpow_horner_BB2_5
	.p2align	2
@ %bb.23:
.Lpow_horner_CPI2_0:
	.long	2146435071                      @ 0x7fefffff
.Lpow_horner_CPI2_1:
	.long	2145386495                      @ 0x7fdfffff
.Lpow_horner_CPI2_2:
	.long	4294966273                      @ 0xfffffc01
.Lpow_horner_CPI2_3:
	.long	1021                            @ 0x3fd
.Lpow_horner_func_end2:
	.size	root64_boundary, .Lpow_horner_func_end2-root64_boundary
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	pow_root128_decide              @ -- Begin function pow_root128_decide
	.p2align	2
	.type	pow_root128_decide,%function
	.code	16
	.thumb_func
pow_root128_decide:                     @ @pow_root128_decide
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#28
	sub	sp, #28
	mov	r5, r2
	ldr	r6, [sp, #52]
	str	r6, [sp, #4]
	ldr	r4, [sp, #48]
	str	r4, [sp]
	str	r0, [sp, #20]                   @ 4-byte Spill
	str	r1, [sp, #24]                   @ 4-byte Spill
	bl	_ZL16root128_boundaryRK13PowInteger128jby
	ldr	r7, .Lpow_horner_CPI3_0
	movs	r2, #0
	cmp	r0, #0
	beq	.Lpow_horner_BB3_5
@ %bb.1:
	ldr	r1, [sp, #56]
	cmp	r1, #0
	beq	.Lpow_horner_BB3_6
@ %bb.2:
	movs	r7, #0
	.inst.n	0x1c65 @ adds	r5, r4, #1
	adcs	r7, r6
	cmp	r0, #0
	bgt	.Lpow_horner_BB3_4
@ %bb.3:
	mov	r5, r4
.Lpow_horner_BB3_4:
	ble	.Lpow_horner_BB3_12
	b	.Lpow_horner_BB3_13
.Lpow_horner_BB3_5:
	mov	r5, r2
	b	.Lpow_horner_BB3_13
.Lpow_horner_BB3_6:
	cmp	r0, #1
	blt	.Lpow_horner_BB3_10
@ %bb.7:
	movs	r0, #0
	.inst.n	0x1c64 @ adds	r4, r4, #1
	str	r4, [sp]
	adcs	r6, r0
	str	r6, [sp, #4]
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r1, [sp, #24]                   @ 4-byte Reload
	mov	r2, r5
	bl	_ZL16root128_boundaryRK13PowInteger128jby
	cmp	r0, #0
	bmi	.Lpow_horner_BB3_9
@ %bb.8:
	mov	r6, r7
.Lpow_horner_BB3_9:
	asrs	r5, r0, #31
	ands	r5, r4
	b	.Lpow_horner_BB3_12
.Lpow_horner_BB3_10:
	str	r2, [sp, #8]                    @ 4-byte Spill
	movs	r0, #0
	mov	r2, r5
	.inst.n	0x1e65 @ subs	r5, r4, #1
	str	r5, [sp]
	mov	r7, r6
	str	r0, [sp, #16]                   @ 4-byte Spill
	sbcs	r7, r0
	str	r7, [sp, #4]
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r1, [sp, #24]                   @ 4-byte Reload
	str	r2, [sp, #12]                   @ 4-byte Spill
	bl	_ZL16root128_boundaryRK13PowInteger128jby
	cmp	r0, #0
	ble	.Lpow_horner_BB3_14
@ %bb.11:
	mov	r5, r4
.Lpow_horner_BB3_12:
	mov	r7, r6
.Lpow_horner_BB3_13:
	mov	r0, r5
	mov	r1, r7
	add	sp, #28
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_BB3_14:
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	ldr	r2, [sp, #12]                   @ 4-byte Reload
	bmi	.Lpow_horner_BB3_16
.Lpow_horner_BB3_15:
	ldr	r5, [sp, #8]                    @ 4-byte Reload
	ldr	r7, .Lpow_horner_CPI3_0
	b	.Lpow_horner_BB3_13
.Lpow_horner_BB3_16:
	.inst.n	0x1ea0 @ subs	r0, r4, #2
	str	r0, [sp]
	sbcs	r6, r1
	str	r6, [sp, #4]
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r1, [sp, #24]                   @ 4-byte Reload
	bl	_ZL16root128_boundaryRK13PowInteger128jby
	cmp	r0, #0
	bgt	.Lpow_horner_BB3_13
	b	.Lpow_horner_BB3_15
	.p2align	2
@ %bb.17:
.Lpow_horner_CPI3_0:
	.long	2146959360                      @ 0x7ff80000
.Lpow_horner_func_end3:
	.size	pow_root128_decide, .Lpow_horner_func_end3-pow_root128_decide
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_boundary_exact,"ax",%progbits
	.p2align	2                               @ -- Begin function _ZL16root128_boundaryRK13PowInteger128jby
	.type	_ZL16root128_boundaryRK13PowInteger128jby,%function
	.code	16
	.thumb_func
_ZL16root128_boundaryRK13PowInteger128jby: @ @_ZL16root128_boundaryRK13PowInteger128jby
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#84
	sub	sp, #84
	ldr	r6, .Lpow_horner_CPI4_0
	ldr	r5, [sp, #108]
	ldr	r7, [sp, #104]
	.inst.n	0x1c7b @ adds	r3, r7, #1
	mov	r4, r5
	sbcs	r4, r6
	ldr	r6, .Lpow_horner_CPI4_1
	.inst.n	0x1e5b @ subs	r3, r3, #1
	adcs	r6, r4
	bhs	.Lpow_horner_BB4_2
@ %bb.1:
	movs	r0, #0
	b	.Lpow_horner_BB4_19
.Lpow_horner_BB4_2:
	str	r2, [sp, #4]                    @ 4-byte Spill
	str	r0, [sp, #8]                    @ 4-byte Spill
	movs	r4, #1
	lsls	r2, r4, #10
	lsls	r3, r7, #11
	adds	r6, r3, r2
	lsrs	r2, r5, #20
	ldr	r3, .Lpow_horner_CPI4_2
	adds	r3, r2, r3
	lsrs	r2, r7, #21
	lsls	r0, r5, #11
	adds	r0, r0, r2
	str	r4, [sp]                        @ 4-byte Spill
	lsls	r7, r4, #31
	orrs	r7, r0
	movs	r0, #0
	cmp	r1, #2
	bhs	.Lpow_horner_BB4_3
	b	.Lpow_horner_BB4_13
.Lpow_horner_BB4_3:
	str	r0, [sp, #48]                   @ 4-byte Spill
	str	r0, [sp, #52]                   @ 4-byte Spill
	str	r0, [sp, #12]                   @ 4-byte Spill
	str	r0, [sp, #40]                   @ 4-byte Spill
	mov	r5, r6
.Lpow_horner_BB4_4:                                @ =>This Inner Loop Header: Depth=1
	str	r5, [sp, #20]                   @ 4-byte Spill
	str	r1, [sp, #36]                   @ 4-byte Spill
	str	r3, [sp, #44]                   @ 4-byte Spill
	lsrs	r6, r5, #16
	uxth	r0, r7
	mov	r2, r6
	muls	r2, r0, r2
	uxth	r4, r5
	mov	r3, r4
	muls	r3, r0, r3
	lsrs	r1, r3, #16
	adds	r5, r1, r2
	lsrs	r1, r5, #16
	str	r7, [sp, #16]                   @ 4-byte Spill
	lsrs	r7, r7, #16
	mov	r2, r6
	muls	r2, r7, r2
	adds	r1, r1, r2
	uxth	r5, r5
	mov	r2, r4
	muls	r2, r7, r2
	adds	r2, r5, r2
	str	r2, [sp, #28]                   @ 4-byte Spill
	lsrs	r2, r2, #16
	adds	r1, r1, r2
	lsrs	r2, r1, #31
	str	r2, [sp, #24]                   @ 4-byte Spill
	lsls	r1, r1, #1
	str	r1, [sp, #32]                   @ 4-byte Spill
	mov	r5, r0
	muls	r5, r7, r5
	muls	r0, r0, r0
	lsrs	r2, r0, #16
	adds	r2, r2, r5
	uxth	r1, r2
	adds	r1, r1, r5
	lsrs	r5, r1, #16
	lsrs	r2, r2, #16
	muls	r7, r7, r7
	adds	r2, r2, r7
	adds	r7, r2, r5
	lsls	r1, r1, #16
	uxth	r0, r0
	adds	r0, r1, r0
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	adds	r0, r0, r1
	str	r0, [sp, #32]                   @ 4-byte Spill
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	adcs	r7, r0
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	lsls	r0, r0, #16
	lsrs	r1, r0, #31
	str	r1, [sp, #28]                   @ 4-byte Spill
	mov	r1, r4
	muls	r1, r6, r1
	muls	r4, r4, r4
	lsrs	r2, r4, #16
	adds	r2, r2, r1
	uxth	r5, r2
	adds	r1, r5, r1
	lsrs	r5, r1, #16
	lsrs	r2, r2, #16
	muls	r6, r6, r6
	adds	r2, r2, r6
	adds	r2, r2, r5
	ldr	r5, [sp, #28]                   @ 4-byte Reload
	uxth	r3, r3
	adds	r0, r0, r3
	lsls	r0, r0, #1
	adds	r2, r0, r2
	ldr	r0, [sp, #32]                   @ 4-byte Reload
	adcs	r5, r0
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	adcs	r7, r0
	lsls	r0, r1, #16
	uxth	r1, r4
	adds	r6, r0, r1
	ldr	r0, [sp, #48]                   @ 4-byte Reload
	mov	r4, r0
	ldr	r1, [sp, #52]                   @ 4-byte Reload
	orrs	r4, r1
	beq	.Lpow_horner_BB4_6
@ %bb.5:                                @   in Loop: Header=BB4_4 Depth=1
	str	r2, [sp, #52]                   @ 4-byte Spill
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	ldr	r3, [sp, #16]                   @ 4-byte Reload
	bl	pow_integer128_approx_high64
	mov	r2, r1
	lsrs	r1, r0, #31
	lsls	r3, r2, #1
	adds	r3, r3, r1
	lsrs	r1, r2, #31
	movs	r2, #0
	adds	r5, r1, r5
	adcs	r7, r2
	lsls	r0, r0, #1
	adds	r0, r0, r6
	str	r0, [sp, #48]                   @ 4-byte Spill
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	adcs	r3, r0
	str	r3, [sp, #52]                   @ 4-byte Spill
	adcs	r5, r2
	adcs	r7, r2
	b	.Lpow_horner_BB4_7
.Lpow_horner_BB4_6:                                @   in Loop: Header=BB4_4 Depth=1
	str	r6, [sp, #48]                   @ 4-byte Spill
	str	r2, [sp, #52]                   @ 4-byte Spill
.Lpow_horner_BB4_7:                                @   in Loop: Header=BB4_4 Depth=1
	ldr	r2, [sp, #40]                   @ 4-byte Reload
	.inst.n	0x1e51 @ subs	r1, r2, #1
	mov	r0, r2
	sbcs	r0, r1
	cmp	r4, #0
	ldr	r3, [sp, #44]                   @ 4-byte Reload
	beq	.Lpow_horner_BB4_9
@ %bb.8:                                @   in Loop: Header=BB4_4 Depth=1
	movs	r0, #16
.Lpow_horner_BB4_9:                                @   in Loop: Header=BB4_4 Depth=1
	lsls	r1, r2, #1
	adds	r4, r0, r1
	lsls	r3, r3, #1
	cmp	r7, #0
	bmi	.Lpow_horner_BB4_11
@ %bb.10:                               @   in Loop: Header=BB4_4 Depth=1
	str	r3, [sp, #44]                   @ 4-byte Spill
	ldr	r3, [sp, #48]                   @ 4-byte Reload
	lsrs	r0, r3, #31
	ldr	r6, [sp, #52]                   @ 4-byte Reload
	lsls	r1, r6, #1
	adds	r0, r1, r0
	lsrs	r1, r5, #31
	lsls	r2, r7, #1
	adds	r7, r2, r1
	lsls	r1, r5, #1
	lsrs	r2, r6, #31
	adds	r5, r1, r2
	lsls	r3, r3, #1
	str	r3, [sp, #48]                   @ 4-byte Spill
	ldr	r3, [sp, #44]                   @ 4-byte Reload
	lsls	r4, r4, #1
	str	r0, [sp, #52]                   @ 4-byte Spill
	b	.Lpow_horner_BB4_12
.Lpow_horner_BB4_11:                               @   in Loop: Header=BB4_4 Depth=1
	movs	r0, #1
	orrs	r3, r0
.Lpow_horner_BB4_12:                               @   in Loop: Header=BB4_4 Depth=1
	str	r4, [sp, #40]                   @ 4-byte Spill
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	lsrs	r0, r1, #1
	cmp	r1, #3
	mov	r1, r0
	bls	.Lpow_horner_BB4_14
	b	.Lpow_horner_BB4_4
.Lpow_horner_BB4_13:
	str	r0, [sp, #48]                   @ 4-byte Spill
	str	r0, [sp, #40]                   @ 4-byte Spill
	str	r0, [sp, #52]                   @ 4-byte Spill
	mov	r5, r6
.Lpow_horner_BB4_14:
	ldr	r0, [sp, #48]                   @ 4-byte Reload
	str	r0, [sp, #64]
	str	r5, [sp, #56]
	ldr	r0, [sp, #40]                   @ 4-byte Reload
	str	r0, [sp, #76]
	str	r3, [sp, #72]
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	str	r0, [sp, #68]
	str	r7, [sp, #60]
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	cmp	r0, #0
	beq	.Lpow_horner_BB4_18
@ %bb.15:
	add	r0, sp, #56
	ldr	r1, [sp, #8]                    @ 4-byte Reload
	bl	pow_integer128_multiply
	movs	r1, #0
	mvns	r0, r1
	ldr	r4, [sp, #72]
	cmp	r4, #0
	bgt	.Lpow_horner_BB4_19
@ %bb.16:
	mvns	r2, r1
	cmp	r4, r2
	bge	.Lpow_horner_BB4_20
@ %bb.17:
	ldr	r0, [sp]                        @ 4-byte Reload
	b	.Lpow_horner_BB4_19
.Lpow_horner_BB4_18:
	add	r1, sp, #56
	ldr	r0, [sp, #8]                    @ 4-byte Reload
	bl	_ZL15root128_compareRK13PowInteger128S1_
.Lpow_horner_BB4_19:
	add	sp, #84
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_BB4_20:
	ldr	r2, [sp, #60]
	ldr	r3, [sp, #56]
	cmp	r4, #0
	beq	.Lpow_horner_BB4_24
@ %bb.21:
	ands	r3, r2
	.inst.n	0x1c58 @ adds	r0, r3, #1
	ldr	r0, [sp]                        @ 4-byte Reload
	bne	.Lpow_horner_BB4_19
@ %bb.22:
	ldr	r0, [sp, #76]
	rsbs	r0, r0, #0
	mov	r2, r1
	sbcs	r2, r1
	ldr	r3, [sp, #68]
	ldr	r4, [sp, #64]
	subs	r0, r4, r0
	sbcs	r3, r2
	bhs	.Lpow_horner_BB4_28
@ %bb.23:
	movs	r0, #1
	b	.Lpow_horner_BB4_19
.Lpow_horner_BB4_24:
	movs	r1, #1
	lsls	r4, r1, #31
	rsbs	r3, r3, #0
	sbcs	r4, r2
	blo	.Lpow_horner_BB4_19
@ %bb.25:
	ldr	r2, [sp, #68]
	movs	r0, #0
	ldr	r3, [sp, #64]
	ldr	r4, [sp, #76]
	subs	r3, r4, r3
	mov	r3, r0
	sbcs	r3, r2
	blo	.Lpow_horner_BB4_27
@ %bb.26:
	mov	r1, r0
.Lpow_horner_BB4_27:
	cmp	r1, #0
	bne	.Lpow_horner_BB4_29
.Lpow_horner_BB4_28:
	mov	r0, r1
	b	.Lpow_horner_BB4_19
.Lpow_horner_BB4_29:
	mvns	r0, r0
	b	.Lpow_horner_BB4_19
	.p2align	2
@ %bb.30:
.Lpow_horner_CPI4_0:
	.long	2146435071                      @ 0x7fefffff
.Lpow_horner_CPI4_1:
	.long	2145386495                      @ 0x7fdfffff
.Lpow_horner_CPI4_2:
	.long	4294966273                      @ 0xfffffc01
.Lpow_horner_func_end4:
	.size	_ZL16root128_boundaryRK13PowInteger128jby, .Lpow_horner_func_end4-_ZL16root128_boundaryRK13PowInteger128jby
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_root_prefix,"ax",%progbits
	.globl	root64_distance                 @ -- Begin function root64_distance
	.p2align	2
	.type	root64_distance,%function
	.code	16
	.thumb_func
root64_distance:                        @ @root64_distance
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#44
	sub	sp, #44
	mov	r4, r0
	ldr	r0, .Lpow_horner_CPI5_0
	.inst.n	0x1c55 @ adds	r5, r2, #1
	mov	r6, r3
	sbcs	r6, r0
	movs	r0, #0
	str	r0, [sp, #40]                   @ 4-byte Spill
	mvns	r1, r0
	mov	r0, r1
	ldr	r7, .Lpow_horner_CPI5_1
	.inst.n	0x1e6d @ subs	r5, r5, #1
	adcs	r7, r6
	bhs	.Lpow_horner_BB5_1
	b	.Lpow_horner_BB5_13
.Lpow_horner_BB5_1:
	ldr	r7, [r4, #12]
	ldr	r5, .Lpow_horner_CPI5_2
	cmp	r7, r5
	bls	.Lpow_horner_BB5_2
	b	.Lpow_horner_BB5_13
.Lpow_horner_BB5_2:
	ldr	r5, [r4, #8]
	lsrs	r6, r3, #20
	adds	r5, r5, r6
	ldr	r6, .Lpow_horner_CPI5_3
	adds	r5, r5, r6
	movs	r6, #2
	mvns	r6, r6
	cmp	r5, r6
	bhs	.Lpow_horner_BB5_3
	b	.Lpow_horner_BB5_13
.Lpow_horner_BB5_3:
	str	r7, [sp, #20]                   @ 4-byte Spill
	str	r0, [sp, #24]                   @ 4-byte Spill
	str	r1, [sp, #28]                   @ 4-byte Spill
	.inst.n	0x1c68 @ adds	r0, r5, #1
	str	r0, [sp, #16]                   @ 4-byte Spill
	lsrs	r5, r2, #21
	lsls	r0, r3, #11
	str	r0, [sp, #12]                   @ 4-byte Spill
	adds	r3, r0, r5
	uxth	r3, r3
	ldr	r0, [r4, #4]
	lsrs	r5, r0, #16
	mov	r7, r3
	muls	r7, r5, r7
	str	r0, [sp]                        @ 4-byte Spill
	uxth	r0, r0
	str	r0, [sp, #32]                   @ 4-byte Spill
	mov	r1, r3
	muls	r1, r0, r1
	str	r1, [sp, #8]                    @ 4-byte Spill
	lsrs	r6, r1, #16
	adds	r7, r6, r7
	lsrs	r0, r7, #16
	str	r0, [sp, #4]                    @ 4-byte Spill
	movs	r0, #1
	str	r0, [sp, #36]                   @ 4-byte Spill
	lsls	r6, r0, #15
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	lsrs	r1, r0, #16
	orrs	r1, r6
	mov	r6, r1
	muls	r6, r5, r6
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	adds	r0, r0, r6
	str	r0, [sp, #12]                   @ 4-byte Spill
	uxth	r7, r7
	mov	r0, r1
	ldr	r6, [sp, #32]                   @ 4-byte Reload
	muls	r0, r6, r0
	adds	r7, r7, r0
	lsrs	r0, r7, #16
	ldr	r6, [sp, #12]                   @ 4-byte Reload
	adds	r0, r6, r0
	str	r0, [sp, #12]                   @ 4-byte Spill
	ldr	r0, [r4]
	lsrs	r4, r0, #16
	mov	r6, r3
	muls	r6, r4, r6
	uxth	r0, r0
	muls	r3, r0, r3
	lsrs	r3, r3, #16
	adds	r3, r3, r6
	lsrs	r6, r3, #16
	muls	r4, r1, r4
	adds	r4, r6, r4
	uxth	r3, r3
	muls	r1, r0, r1
	adds	r0, r3, r1
	lsrs	r0, r0, #16
	adds	r0, r4, r0
	lsls	r1, r7, #16
	ldr	r3, [sp, #8]                    @ 4-byte Reload
	uxth	r3, r3
	adds	r1, r1, r3
	adds	r4, r1, r0
	ldr	r7, [sp, #40]                   @ 4-byte Reload
	mov	r3, r7
	adcs	r3, r7
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	lsls	r0, r0, #10
	lsls	r1, r2, #11
	adds	r0, r1, r0
	uxth	r0, r0
	mov	r2, r0
	muls	r2, r5, r2
	ldr	r6, [sp, #32]                   @ 4-byte Reload
	muls	r0, r6, r0
	lsrs	r0, r0, #16
	adds	r0, r0, r2
	lsrs	r2, r0, #16
	lsrs	r1, r1, #16
	muls	r5, r1, r5
	adds	r2, r2, r5
	ldr	r5, [sp, #12]                   @ 4-byte Reload
	uxth	r0, r0
	muls	r1, r6, r1
	adds	r0, r0, r1
	lsrs	r0, r0, #16
	adds	r0, r2, r0
	adds	r1, r4, r0
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	adcs	r5, r3
	adds	r2, r4, r0
	adcs	r3, r7
	.inst.n	0x1c88 @ adds	r0, r1, #2
	bne	.Lpow_horner_BB5_5
@ %bb.4:
	.inst.n	0x1e50 @ subs	r0, r2, #1
	sbcs	r5, r7
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	lsls	r1, r1, #30
	adds	r0, r0, r1
	adcs	r5, r7
	ldr	r1, [sp, #28]                   @ 4-byte Reload
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	ldr	r6, [sp, #20]                   @ 4-byte Reload
	bhs	.Lpow_horner_BB5_12
	b	.Lpow_horner_BB5_13
.Lpow_horner_BB5_5:
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	cmp	r1, #0
	ldr	r6, [sp, #20]                   @ 4-byte Reload
	beq	.Lpow_horner_BB5_7
@ %bb.6:
	lsls	r4, r0, #31
	b	.Lpow_horner_BB5_8
.Lpow_horner_BB5_7:
	lsls	r4, r0, #30
.Lpow_horner_BB5_8:
	ldr	r1, [sp, #28]                   @ 4-byte Reload
	subs	r3, r5, r4
	adcs	r7, r7
	eors	r7, r0
	rsbs	r0, r7, #0
	eors	r3, r0
	eors	r2, r0
	mov	r7, r5
	subs	r5, r2, r0
	sbcs	r3, r0
	cmp	r7, r4
	blo	.Lpow_horner_BB5_10
@ %bb.9:
	mov	r2, r5
	b	.Lpow_horner_BB5_11
.Lpow_horner_BB5_10:
	rsbs	r2, r5, #0
.Lpow_horner_BB5_11:
	lsrs	r0, r5, #30
	orrs	r3, r0
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	bne	.Lpow_horner_BB5_13
.Lpow_horner_BB5_12:
	lsls	r0, r6, #11
	ldr	r1, [sp]                        @ 4-byte Reload
	lsrs	r1, r1, #21
	adds	r0, r0, r1
	movs	r1, #3
	lsls	r1, r1, #11
	adds	r1, r0, r1
	mov	r0, r2
.Lpow_horner_BB5_13:
	add	sp, #44
	pop	{r4, r5, r6, r7, pc}
	.p2align	2
@ %bb.14:
.Lpow_horner_CPI5_0:
	.long	2146435071                      @ 0x7fefffff
.Lpow_horner_CPI5_1:
	.long	2145386495                      @ 0x7fdfffff
.Lpow_horner_CPI5_2:
	.long	65532                           @ 0xfffc
.Lpow_horner_CPI5_3:
	.long	4294966272                      @ 0xfffffc00
.Lpow_horner_func_end5:
	.size	root64_distance, .Lpow_horner_func_end5-root64_distance
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	factor64_base                   @ -- Begin function factor64_base
	.p2align	1
	.type	factor64_base,%function
	.code	16
	.thumb_func
factor64_base:                          @ @factor64_base
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#24
	sub	sp, #24
	str	r0, [sp, #12]                   @ 4-byte Spill
	ldr	r3, [r1, #8]
	ldr	r2, [r0, #8]
	adds	r2, r2, r3
	str	r2, [sp]                        @ 4-byte Spill
	str	r2, [r0, #8]
	ldr	r2, [r0, #4]
	lsrs	r6, r2, #16
	ldr	r0, [r1, #4]
	uxth	r4, r0
	str	r0, [sp, #20]                   @ 4-byte Spill
	mov	r3, r6
	muls	r3, r4, r3
	uxth	r7, r2
	mov	r2, r7
	muls	r2, r4, r2
	str	r2, [sp, #4]                    @ 4-byte Spill
	lsrs	r5, r2, #16
	adds	r3, r5, r3
	lsrs	r5, r3, #16
	lsrs	r0, r0, #16
	str	r0, [sp, #8]                    @ 4-byte Spill
	mov	r2, r6
	muls	r2, r0, r2
	adds	r2, r5, r2
	uxth	r3, r3
	mov	r5, r7
	muls	r5, r0, r5
	adds	r3, r3, r5
	lsrs	r5, r3, #16
	adds	r0, r2, r5
	str	r0, [sp, #16]                   @ 4-byte Spill
	ldr	r1, [r1]
	uxth	r2, r1
	mov	r5, r2
	muls	r5, r6, r5
	muls	r2, r7, r2
	lsrs	r2, r2, #16
	adds	r2, r2, r5
	lsrs	r5, r2, #16
	lsrs	r1, r1, #16
	muls	r6, r1, r6
	adds	r5, r5, r6
	uxth	r2, r2
	muls	r1, r7, r1
	adds	r1, r2, r1
	lsrs	r1, r1, #16
	adds	r2, r5, r1
	lsls	r1, r3, #16
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	uxth	r0, r0
	adds	r0, r1, r0
	movs	r1, #0
	adds	r0, r0, r2
	adcs	r1, r1
	ldr	r6, [sp, #12]                   @ 4-byte Reload
	ldr	r2, [r6]
	lsrs	r3, r2, #16
	mov	r5, r3
	muls	r5, r4, r5
	uxth	r2, r2
	muls	r4, r2, r4
	lsrs	r4, r4, #16
	adds	r4, r4, r5
	lsrs	r5, r4, #16
	ldr	r7, [sp, #8]                    @ 4-byte Reload
	muls	r3, r7, r3
	adds	r3, r5, r3
	uxth	r4, r4
	muls	r2, r7, r2
	adds	r2, r4, r2
	lsrs	r2, r2, #16
	adds	r2, r3, r2
	mov	r3, r6
	adds	r4, r0, r2
	ldr	r0, [sp, #16]                   @ 4-byte Reload
	adcs	r1, r0
	ldr	r0, [r6, #12]
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	lsrs	r2, r2, #24
	.inst.n	0x1c52 @ adds	r2, r2, #1
	muls	r2, r0, r2
	adds	r2, #255
	lsrs	r0, r2, #8
	.inst.n	0x1cc0 @ adds	r0, r0, #3
	cmp	r1, #0
	bmi	.Lpow_horner_BB6_2
@ %bb.1:
	lsrs	r2, r4, #31
	lsls	r1, r1, #1
	adds	r1, r1, r2
	lsls	r4, r4, #1
	lsls	r0, r0, #1
	b	.Lpow_horner_BB6_3
.Lpow_horner_BB6_2:
	ldr	r2, [sp]                        @ 4-byte Reload
	.inst.n	0x1c52 @ adds	r2, r2, #1
	str	r2, [r3, #8]
.Lpow_horner_BB6_3:
	str	r4, [r3]
	str	r0, [r3, #12]
	str	r1, [r3, #4]
	add	sp, #24
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end6:
	.size	factor64_base, .Lpow_horner_func_end6-factor64_base
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_near_one_refine,"ax",%progbits
	.globl	pow_integer128_multiply         @ -- Begin function pow_integer128_multiply
	.p2align	1
	.type	pow_integer128_multiply,%function
	.code	16
	.thumb_func
pow_integer128_multiply:                @ @pow_integer128_multiply
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#68
	sub	sp, #68
	str	r1, [sp, #56]                   @ 4-byte Spill
	str	r0, [sp, #60]                   @ 4-byte Spill
	ldr	r3, [r0]
	lsrs	r6, r3, #16
	ldr	r2, [r1]
	uxth	r4, r2
	mov	r0, r6
	str	r6, [sp, #44]                   @ 4-byte Spill
	muls	r0, r4, r0
	str	r3, [sp, #24]                   @ 4-byte Spill
	uxth	r3, r3
	mov	r1, r3
	str	r3, [sp, #40]                   @ 4-byte Spill
	muls	r1, r4, r1
	str	r1, [sp, #52]                   @ 4-byte Spill
	lsrs	r1, r1, #16
	adds	r0, r1, r0
	lsrs	r7, r0, #16
	str	r2, [sp, #16]                   @ 4-byte Spill
	lsrs	r1, r2, #16
	muls	r6, r1, r6
	adds	r2, r7, r6
	uxth	r0, r0
	muls	r3, r1, r3
	adds	r0, r0, r3
	str	r0, [sp, #48]                   @ 4-byte Spill
	lsrs	r0, r0, #16
	adds	r2, r2, r0
	str	r2, [sp, #32]                   @ 4-byte Spill
	ldr	r0, [sp, #60]                   @ 4-byte Reload
	ldr	r0, [r0, #4]
	lsrs	r5, r0, #16
	mov	r3, r5
	muls	r3, r4, r3
	str	r0, [sp, #20]                   @ 4-byte Spill
	uxth	r7, r0
	muls	r4, r7, r4
	lsrs	r6, r4, #16
	adds	r3, r6, r3
	lsrs	r6, r3, #16
	mov	r0, r5
	muls	r0, r1, r0
	adds	r0, r6, r0
	uxth	r3, r3
	muls	r1, r7, r1
	adds	r1, r3, r1
	lsrs	r3, r1, #16
	lsls	r1, r1, #16
	uxth	r4, r4
	adds	r1, r1, r4
	str	r1, [sp, #64]                   @ 4-byte Spill
	adds	r1, r2, r1
	mov	r1, r0
	adcs	r1, r3
	str	r1, [sp, #36]                   @ 4-byte Spill
	adds	r0, r0, r3
	str	r0, [sp, #28]                   @ 4-byte Spill
	ldr	r0, [sp, #56]                   @ 4-byte Reload
	ldr	r2, [r0, #4]
	uxth	r6, r2
	mov	r0, r5
	muls	r0, r6, r0
	mov	r3, r7
	muls	r7, r6, r7
	lsrs	r1, r7, #16
	adds	r0, r1, r0
	lsrs	r4, r0, #16
	str	r2, [sp, #12]                   @ 4-byte Spill
	lsrs	r1, r2, #16
	muls	r5, r1, r5
	adds	r4, r4, r5
	uxth	r0, r0
	muls	r3, r1, r3
	adds	r0, r0, r3
	lsrs	r5, r0, #16
	lsls	r0, r0, #16
	uxth	r2, r7
	ldr	r7, [sp, #60]                   @ 4-byte Reload
	adds	r2, r0, r2
	ldr	r0, [sp, #64]                   @ 4-byte Reload
	ldr	r3, [sp, #32]                   @ 4-byte Reload
	adds	r0, r3, r0
	str	r0, [sp, #32]                   @ 4-byte Spill
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	adcs	r0, r2
	adcs	r5, r4
	str	r5, [sp, #64]                   @ 4-byte Spill
	ldr	r5, [sp, #44]                   @ 4-byte Reload
	mov	r3, r5
	muls	r3, r6, r3
	ldr	r0, [sp, #40]                   @ 4-byte Reload
	muls	r6, r0, r6
	lsrs	r4, r6, #16
	adds	r3, r4, r3
	lsrs	r4, r3, #16
	muls	r5, r1, r5
	adds	r4, r4, r5
	uxth	r3, r3
	muls	r0, r1, r0
	adds	r1, r3, r0
	lsrs	r3, r1, #16
	lsls	r1, r1, #16
	uxth	r5, r6
	adds	r1, r1, r5
	ldr	r0, [sp, #32]                   @ 4-byte Reload
	adds	r0, r1, r0
	str	r0, [sp, #28]                   @ 4-byte Spill
	adcs	r3, r4
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	adds	r0, r2, r0
	movs	r6, #0
	adds	r4, r0, r3
	ldr	r0, [sp, #64]                   @ 4-byte Reload
	adcs	r0, r6
	str	r0, [sp, #64]                   @ 4-byte Spill
	ldr	r0, [sp, #48]                   @ 4-byte Reload
	lsls	r0, r0, #16
	ldr	r1, [sp, #52]                   @ 4-byte Reload
	uxth	r1, r1
	adds	r3, r0, r1
	ldr	r0, [r7, #20]
	str	r0, [sp, #48]                   @ 4-byte Spill
	ldr	r2, [sp, #56]                   @ 4-byte Reload
	ldr	r0, [r2, #20]
	str	r0, [sp, #40]                   @ 4-byte Spill
	ldr	r0, [r7, #16]
	str	r0, [sp, #36]                   @ 4-byte Spill
	ldr	r0, [r2, #16]
	str	r0, [sp, #32]                   @ 4-byte Spill
	ldr	r1, [r7, #12]
	ldr	r0, [r7, #8]
	mov	r7, r0
	orrs	r7, r1
	ldr	r5, [r2, #12]
	str	r5, [sp, #44]                   @ 4-byte Spill
	ldr	r2, [r2, #8]
	str	r2, [sp, #52]                   @ 4-byte Spill
	str	r1, [sp, #4]                    @ 4-byte Spill
	str	r0, [sp]                        @ 4-byte Spill
	str	r6, [sp, #8]                    @ 4-byte Spill
	beq	.Lpow_horner_BB7_2
@ %bb.1:
	ldr	r2, [sp, #16]                   @ 4-byte Reload
	mov	r5, r3
	ldr	r3, [sp, #12]                   @ 4-byte Reload
	bl	pow_integer128_approx_high64
	mov	r3, r5
	mov	r5, r1
	adds	r3, r0, r3
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	adcs	r5, r0
	adcs	r4, r6
	str	r4, [sp, #56]                   @ 4-byte Spill
	ldr	r0, [sp, #64]                   @ 4-byte Reload
	adcs	r0, r6
	str	r0, [sp, #64]                   @ 4-byte Spill
	b	.Lpow_horner_BB7_3
.Lpow_horner_BB7_2:
	str	r4, [sp, #56]                   @ 4-byte Spill
	ldr	r5, [sp, #28]                   @ 4-byte Reload
.Lpow_horner_BB7_3:
	ldr	r0, [sp, #48]                   @ 4-byte Reload
	ldr	r1, [sp, #40]                   @ 4-byte Reload
	adds	r0, r1, r0
	str	r0, [sp, #48]                   @ 4-byte Spill
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	adds	r6, r1, r0
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	mov	r0, r2
	ldr	r4, [sp, #44]                   @ 4-byte Reload
	orrs	r0, r4
	beq	.Lpow_horner_BB7_6
@ %bb.4:
	str	r6, [sp, #40]                   @ 4-byte Spill
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	ldr	r1, [sp, #20]                   @ 4-byte Reload
	mov	r6, r4
	mov	r4, r3
	mov	r3, r6
	bl	pow_integer128_approx_high64
	adds	r3, r0, r4
	adcs	r1, r5
	ldr	r0, [sp, #56]                   @ 4-byte Reload
	ldr	r2, [sp, #8]                    @ 4-byte Reload
	adcs	r0, r2
	str	r0, [sp, #56]                   @ 4-byte Spill
	ldr	r0, [sp, #64]                   @ 4-byte Reload
	adcs	r0, r2
	str	r0, [sp, #64]                   @ 4-byte Spill
	cmp	r7, #0
	beq	.Lpow_horner_BB7_7
@ %bb.5:
	movs	r0, #16
	ldr	r6, [sp, #40]                   @ 4-byte Reload
	b	.Lpow_horner_BB7_11
.Lpow_horner_BB7_6:
	mov	r1, r5
	b	.Lpow_horner_BB7_8
.Lpow_horner_BB7_7:
	mov	r4, r6
	ldr	r6, [sp, #40]                   @ 4-byte Reload
.Lpow_horner_BB7_8:
	ldr	r0, [sp]                        @ 4-byte Reload
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	orrs	r2, r0
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	orrs	r4, r0
	orrs	r4, r2
	beq	.Lpow_horner_BB7_10
@ %bb.9:
	movs	r0, #8
	b	.Lpow_horner_BB7_11
.Lpow_horner_BB7_10:
	ldr	r0, [sp, #48]                   @ 4-byte Reload
	.inst.n	0x1e42 @ subs	r2, r0, #1
	sbcs	r0, r2
.Lpow_horner_BB7_11:
	ldr	r2, [sp, #60]                   @ 4-byte Reload
	str	r6, [r2, #16]
	ldr	r5, [sp, #48]                   @ 4-byte Reload
	adds	r0, r0, r5
	ldr	r4, [sp, #64]                   @ 4-byte Reload
	cmp	r4, #0
	bmi	.Lpow_horner_BB7_13
@ %bb.12:
	lsrs	r2, r3, #31
	mov	r5, r3
	lsls	r3, r1, #1
	adds	r2, r3, r2
	ldr	r6, [sp, #56]                   @ 4-byte Reload
	lsrs	r3, r6, #31
	lsls	r4, r4, #1
	adds	r4, r4, r3
	lsls	r3, r6, #1
	lsrs	r1, r1, #31
	adds	r1, r3, r1
	lsls	r3, r5, #1
	lsls	r0, r0, #1
	b	.Lpow_horner_BB7_14
.Lpow_horner_BB7_13:
	.inst.n	0x1c72 @ adds	r2, r6, #1
	ldr	r5, [sp, #60]                   @ 4-byte Reload
	str	r2, [r5, #16]
	mov	r2, r1
	ldr	r1, [sp, #56]                   @ 4-byte Reload
.Lpow_horner_BB7_14:
	ldr	r5, [sp, #60]                   @ 4-byte Reload
	str	r3, [r5, #8]
	str	r1, [r5]
	str	r0, [r5, #20]
	str	r2, [r5, #12]
	str	r4, [r5, #4]
	add	sp, #68
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end7:
	.size	pow_integer128_multiply, .Lpow_horner_func_end7-pow_integer128_multiply
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_square_fixed,"ax",%progbits
	.globl	pow_integer128_square           @ -- Begin function pow_integer128_square
	.p2align	1
	.type	pow_integer128_square,%function
	.code	16
	.thumb_func
pow_integer128_square:                  @ @pow_integer128_square
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#28
	sub	sp, #28
	mov	r7, r0
	ldr	r0, [r0]
	lsrs	r4, r0, #16
	ldr	r1, [r7, #4]
	uxth	r6, r1
	mov	r2, r4
	muls	r2, r6, r2
	str	r0, [sp, #8]                    @ 4-byte Spill
	uxth	r0, r0
	mov	r3, r0
	muls	r3, r6, r3
	str	r3, [sp, #24]                   @ 4-byte Spill
	lsrs	r3, r3, #16
	adds	r2, r3, r2
	lsrs	r5, r2, #16
	str	r1, [sp, #4]                    @ 4-byte Spill
	lsrs	r3, r1, #16
	mov	r1, r4
	muls	r1, r3, r1
	adds	r1, r5, r1
	uxth	r2, r2
	mov	r5, r0
	muls	r5, r3, r5
	adds	r2, r2, r5
	str	r2, [sp, #16]                   @ 4-byte Spill
	lsrs	r5, r2, #16
	adds	r1, r1, r5
	lsrs	r2, r1, #31
	str	r2, [sp, #12]                   @ 4-byte Spill
	lsls	r1, r1, #1
	str	r1, [sp, #20]                   @ 4-byte Spill
	mov	r1, r6
	muls	r1, r3, r1
	muls	r6, r6, r6
	lsrs	r5, r6, #16
	adds	r5, r5, r1
	uxth	r2, r5
	adds	r1, r2, r1
	lsrs	r2, r1, #16
	lsrs	r5, r5, #16
	muls	r3, r3, r3
	adds	r3, r5, r3
	adds	r5, r3, r2
	lsls	r1, r1, #16
	uxth	r2, r6
	adds	r1, r1, r2
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	adds	r1, r1, r2
	str	r1, [sp, #20]                   @ 4-byte Spill
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	adcs	r5, r1
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	lsls	r2, r1, #16
	lsrs	r1, r2, #31
	str	r1, [sp, #12]                   @ 4-byte Spill
	mov	r1, r0
	muls	r1, r4, r1
	muls	r0, r0, r0
	lsrs	r3, r0, #16
	adds	r3, r3, r1
	uxth	r6, r3
	adds	r1, r6, r1
	lsrs	r6, r1, #16
	lsrs	r3, r3, #16
	muls	r4, r4, r4
	adds	r3, r3, r4
	adds	r3, r3, r6
	ldr	r6, [sp, #12]                   @ 4-byte Reload
	ldr	r4, [sp, #24]                   @ 4-byte Reload
	uxth	r4, r4
	adds	r2, r2, r4
	lsls	r2, r2, #1
	movs	r4, #0
	adds	r2, r2, r3
	str	r2, [sp, #16]                   @ 4-byte Spill
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	adcs	r6, r2
	adcs	r5, r4
	lsls	r1, r1, #16
	uxth	r0, r0
	adds	r3, r1, r0
	ldr	r1, [r7, #12]
	ldr	r0, [r7, #8]
	mov	r2, r0
	orrs	r2, r1
	str	r2, [sp, #20]                   @ 4-byte Spill
	beq	.Lpow_horner_BB8_2
@ %bb.1:
	ldr	r2, [sp, #8]                    @ 4-byte Reload
	str	r4, [sp, #12]                   @ 4-byte Spill
	mov	r4, r3
	ldr	r3, [sp, #4]                    @ 4-byte Reload
	bl	pow_integer128_approx_high64
	lsrs	r2, r0, #31
	lsls	r3, r1, #1
	adds	r2, r3, r2
	lsrs	r1, r1, #31
	adds	r6, r1, r6
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	adcs	r5, r1
	lsls	r0, r0, #1
	adds	r4, r0, r4
	str	r4, [sp, #24]                   @ 4-byte Spill
	ldr	r0, [sp, #16]                   @ 4-byte Reload
	adcs	r2, r0
	adcs	r6, r1
	adcs	r5, r1
	b	.Lpow_horner_BB8_3
.Lpow_horner_BB8_2:
	str	r3, [sp, #24]                   @ 4-byte Spill
	ldr	r2, [sp, #16]                   @ 4-byte Reload
.Lpow_horner_BB8_3:
	ldr	r0, [r7, #16]
	lsls	r1, r0, #1
	str	r1, [r7, #16]
	ldr	r0, [r7, #20]
	.inst.n	0x1e44 @ subs	r4, r0, #1
	mov	r3, r0
	sbcs	r3, r4
	ldr	r4, [sp, #20]                   @ 4-byte Reload
	cmp	r4, #0
	beq	.Lpow_horner_BB8_5
@ %bb.4:
	movs	r3, #16
.Lpow_horner_BB8_5:
	lsls	r0, r0, #1
	adds	r0, r3, r0
	cmp	r5, #0
	bmi	.Lpow_horner_BB8_7
@ %bb.6:
	str	r0, [sp, #20]                   @ 4-byte Spill
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	lsrs	r1, r0, #31
	lsls	r3, r2, #1
	adds	r1, r3, r1
	lsrs	r3, r6, #31
	lsls	r4, r5, #1
	adds	r5, r4, r3
	lsls	r3, r6, #1
	lsrs	r2, r2, #31
	adds	r6, r3, r2
	mov	r3, r0
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	lsls	r3, r3, #1
	lsls	r0, r0, #1
	mov	r2, r1
	b	.Lpow_horner_BB8_8
.Lpow_horner_BB8_7:
	movs	r3, #1
	orrs	r1, r3
	str	r1, [r7, #16]
	ldr	r3, [sp, #24]                   @ 4-byte Reload
.Lpow_horner_BB8_8:
	str	r3, [r7, #8]
	str	r6, [r7]
	str	r0, [r7, #20]
	str	r2, [r7, #12]
	str	r5, [r7, #4]
	add	sp, #28
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end8:
	.size	pow_integer128_square, .Lpow_horner_func_end8-pow_integer128_square
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_root_prefix,"ax",%progbits
	.globl	factor64_multiply               @ -- Begin function factor64_multiply
	.p2align	1
	.type	factor64_multiply,%function
	.code	16
	.thumb_func
factor64_multiply:                      @ @factor64_multiply
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#28
	sub	sp, #28
	str	r1, [sp, #24]                   @ 4-byte Spill
	str	r0, [sp, #8]                    @ 4-byte Spill
	ldr	r3, [r1, #8]
	ldr	r2, [r0, #8]
	adds	r2, r2, r3
	str	r2, [sp]                        @ 4-byte Spill
	str	r2, [r0, #8]
	ldr	r2, [r0, #4]
	str	r2, [sp, #20]                   @ 4-byte Spill
	lsrs	r4, r2, #16
	ldr	r0, [r1, #4]
	uxth	r6, r0
	str	r0, [sp, #16]                   @ 4-byte Spill
	mov	r1, r4
	muls	r1, r6, r1
	uxth	r5, r2
	mov	r2, r5
	muls	r2, r6, r2
	lsrs	r7, r2, #16
	adds	r1, r7, r1
	lsrs	r3, r1, #16
	lsrs	r7, r0, #16
	mov	r0, r4
	muls	r0, r7, r0
	adds	r0, r3, r0
	uxth	r1, r1
	mov	r3, r5
	muls	r3, r7, r3
	adds	r1, r1, r3
	str	r1, [sp, #4]                    @ 4-byte Spill
	lsrs	r3, r1, #16
	adds	r0, r0, r3
	str	r0, [sp, #12]                   @ 4-byte Spill
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	ldr	r1, [r0]
	uxth	r3, r1
	mov	r0, r3
	muls	r0, r4, r0
	muls	r3, r5, r3
	lsrs	r3, r3, #16
	adds	r0, r3, r0
	lsrs	r3, r0, #16
	lsrs	r1, r1, #16
	muls	r4, r1, r4
	adds	r3, r3, r4
	uxth	r0, r0
	muls	r1, r5, r1
	adds	r0, r0, r1
	lsrs	r0, r0, #16
	adds	r0, r3, r0
	ldr	r1, [sp, #4]                    @ 4-byte Reload
	lsls	r1, r1, #16
	uxth	r2, r2
	adds	r1, r1, r2
	movs	r5, #0
	adds	r0, r1, r0
	str	r0, [sp, #4]                    @ 4-byte Spill
	adcs	r5, r5
	ldr	r0, [sp, #8]                    @ 4-byte Reload
	ldr	r1, [r0]
	lsrs	r2, r1, #16
	mov	r3, r2
	muls	r3, r6, r3
	uxth	r1, r1
	muls	r6, r1, r6
	lsrs	r4, r6, #16
	adds	r3, r4, r3
	lsrs	r4, r3, #16
	muls	r2, r7, r2
	adds	r2, r4, r2
	uxth	r3, r3
	muls	r1, r7, r1
	adds	r1, r3, r1
	mov	r3, r0
	lsrs	r1, r1, #16
	adds	r1, r2, r1
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	adds	r6, r0, r1
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	adcs	r5, r0
	ldr	r0, [r3, #12]
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	lsrs	r1, r1, #24
	.inst.n	0x1c49 @ adds	r1, r1, #1
	muls	r1, r0, r1
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	ldr	r0, [r0, #12]
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	lsrs	r2, r2, #24
	.inst.n	0x1c52 @ adds	r2, r2, #1
	muls	r2, r0, r2
	adds	r0, r2, r1
	adds	r0, #255
	lsrs	r0, r0, #8
	.inst.n	0x1d00 @ adds	r0, r0, #4
	cmp	r5, #0
	bmi	.Lpow_horner_BB9_2
@ %bb.1:
	lsrs	r1, r6, #31
	lsls	r2, r5, #1
	adds	r5, r2, r1
	lsls	r6, r6, #1
	lsls	r0, r0, #1
	b	.Lpow_horner_BB9_3
.Lpow_horner_BB9_2:
	ldr	r1, [sp]                        @ 4-byte Reload
	.inst.n	0x1c49 @ adds	r1, r1, #1
	str	r1, [r3, #8]
.Lpow_horner_BB9_3:
	str	r6, [r3]
	str	r0, [r3, #12]
	str	r5, [r3, #4]
	add	sp, #28
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end9:
	.size	factor64_multiply, .Lpow_horner_func_end9-factor64_multiply
	.cantunwind
	.fnend
                                        @ -- End function
/* Caller proves y.low32=0 and unbiased y exponent in[-7,5].
 * Reproduce the original root prefix frame, normal-x and dyadic-y
 * checks and register/spill state. Its unchanged body starts at BB10_4. */
.p2align 2
.global pow_root128_ranged
.hidden pow_root128_ranged
.type pow_root128_ranged,%function
.thumb_func
pow_root128_ranged:
 push {r4-r7,lr}
 sub sp,#108
 ldr r5,.Lroot_ranged_nan
 movs r6,#0
 lsrs r2,r1,#20
 ldr r7,.Lroot_ranged_x_limit
 adds r4,r2,r7
 subs r4,#1
 cmp r4,r7
 blo .Lpow_horner_BB10_17
 lsls r4,r3,#16
 bne .Lpow_horner_BB10_17
 lsls r4,r3,#1
 lsrs r4,#21
 ldr r7,.Lroot_ranged_exponent
 str r4,[sp,#52]
 b .Lroot_ranged_body
.p2align 2
.Lroot_ranged_nan: .word 0x7ff80000
.Lroot_ranged_x_limit: .word 0xfffff802
.Lroot_ranged_exponent: .word 0xfffffbfd
.size pow_root128_ranged,.-pow_root128_ranged

	.globl	pow_root128                     @ -- Begin function pow_root128
	.p2align	2
	.type	pow_root128,%function
	.code	16
	.thumb_func
pow_root128:                            @ @pow_root128
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#108
	sub	sp, #108
	ldr	r5, .Lpow_horner_CPI10_17
	movs	r6, #0
	cmp	r2, #0
	bne	.Lpow_horner_BB10_17
@ %bb.1:
	lsrs	r2, r1, #20
	ldr	r7, .Lpow_horner_CPI10_18
	adds	r4, r2, r7
	.inst.n	0x1e64 @ subs	r4, r4, #1
	cmp	r4, r7
	blo	.Lpow_horner_BB10_17
@ %bb.2:
	lsls	r4, r3, #16
	bne	.Lpow_horner_BB10_17
@ %bb.3:
	lsls	r4, r3, #1
	lsrs	r4, r4, #21
	ldr	r7, .Lpow_horner_CPI10_19
	str	r4, [sp, #52]                   @ 4-byte Spill
	adds	r4, r4, r7
	adds	r4, #11
	cmp	r4, #12
	bhi	.Lpow_horner_BB10_17
.Lroot_ranged_body:
@ %bb.4:
	str	r6, [sp, #48]                   @ 4-byte Spill
	str	r5, [sp, #36]                   @ 4-byte Spill
	lsls	r4, r3, #12
	lsrs	r4, r4, #28
	adds	r4, #16
	lsrs	r6, r4, #2
	.inst.n	0x1cbd @ adds	r5, r7, #2
	str	r3, [sp, #40]                   @ 4-byte Spill
	lsls	r7, r3, #14
	lsrs	r7, r7, #30
	cmp	r7, #0
	beq	.Lpow_horner_BB10_6
@ %bb.5:
	ldr	r5, .Lpow_horner_CPI10_13
.Lpow_horner_BB10_6:
	beq	.Lpow_horner_BB10_8
@ %bb.7:
	mov	r6, r4
.Lpow_horner_BB10_8:
	movs	r4, #1
	mov	r7, r4
	bics	r7, r6
	lsrs	r6, r7
	str	r4, [sp, #44]                   @ 4-byte Spill
	bics	r4, r6
	ldr	r3, [sp, #52]                   @ 4-byte Reload
	adds	r3, r5, r3
	adds	r3, r3, r7
	adds	r3, r3, r4
	.inst.n	0x1f9d @ subs	r5, r3, #6
	movs	r7, #12
	mvns	r7, r7
	cmp	r5, r7
	blo	.Lpow_horner_BB10_15
@ %bb.9:
	lsrs	r6, r4
	cmp	r3, #0
	bmi	.Lpow_horner_BB10_12
@ %bb.10:
	lsls	r6, r3
	cmp	r6, #32
	bhi	.Lpow_horner_BB10_15
@ %bb.11:
	movs	r7, #1
	b	.Lpow_horner_BB10_13
.Lpow_horner_BB10_12:
	rsbs	r4, r3, #0
	ldr	r7, [sp, #44]                   @ 4-byte Reload
	lsls	r7, r4
.Lpow_horner_BB10_13:
	ldr	r5, .Lpow_horner_CPI10_13
	adds	r2, r5, r2
	.inst.n	0x1d12 @ adds	r2, r2, #4
	mov	r4, r2
	muls	r4, r6, r4
	.inst.n	0x1dad @ adds	r5, r5, #6
	muls	r5, r7, r5
	cmp	r4, r5
	blt	.Lpow_horner_BB10_15
@ %bb.14:
	ldr	r5, .Lpow_horner_CPI10_14
	muls	r5, r7, r5
	adds	r4, r4, r6
	cmp	r4, r5
	ble	.Lpow_horner_BB10_18
.Lpow_horner_BB10_15:
	ldr	r5, .Lpow_horner_CPI10_11
.Lpow_horner_BB10_16:
	ldr	r6, [sp, #48]                   @ 4-byte Reload
.Lpow_horner_BB10_17:
	mov	r0, r6
	mov	r1, r5
	add	sp, #108
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_BB10_18:
	cmp	r7, #1
	beq	.Lpow_horner_BB10_24
@ %bb.19:
	ldr	r4, [sp, #40]                   @ 4-byte Reload
	cmp	r4, #0
	bmi	.Lpow_horner_BB10_23
@ %bb.20:
	cmp	r6, #4
	blo	.Lpow_horner_BB10_24
@ %bb.21:
	lsls	r4, r7, #1
	cmp	r6, r4
	bhs	.Lpow_horner_BB10_24
.Lpow_horner_BB10_22:
	ldr	r2, [sp, #40]                   @ 4-byte Reload
	lsrs	r2, r2, #31
	str	r2, [sp]
	rsbs	r3, r3, #0
	mov	r2, r6
	bl	_ZL10factor_powyjjb
	mov	r6, r0
	mov	r5, r1
	b	.Lpow_horner_BB10_17
.Lpow_horner_BB10_23:
	cmp	r6, r7
	blo	.Lpow_horner_BB10_22
.Lpow_horner_BB10_24:
	movs	r3, #0
	str	r3, [sp, #92]
	str	r3, [sp, #88]
	str	r3, [sp, #16]                   @ 4-byte Spill
	str	r3, [sp, #100]
	str	r2, [sp, #96]
	lsls	r2, r0, #11
	str	r2, [sp, #80]
	lsrs	r0, r0, #21
	lsls	r1, r1, #11
	adds	r0, r1, r0
	ldr	r2, [sp, #44]                   @ 4-byte Reload
	lsls	r1, r2, #31
	str	r1, [sp, #52]                   @ 4-byte Spill
	orrs	r0, r1
	str	r0, [sp, #84]
	cmp	r6, #1
	beq	.Lpow_horner_BB10_38
@ %bb.25:
	cmp	r6, #7
	bhi	.Lpow_horner_BB10_27
@ %bb.26:
	mov	r0, r6
	b	.Lpow_horner_BB10_28
.Lpow_horner_BB10_27:
	lsrs	r0, r6, #3
.Lpow_horner_BB10_28:
	cmp	r0, #1
	bhi	.Lpow_horner_BB10_30
@ %bb.29:
	movs	r2, #0
.Lpow_horner_BB10_30:
	cmp	r6, #7
	bls	.Lpow_horner_BB10_32
@ %bb.31:
	.inst.n	0x1cd2 @ adds	r2, r2, #3
.Lpow_horner_BB10_32:
	str	r2, [sp, #44]                   @ 4-byte Spill
	add	r1, sp, #80
	add	r2, sp, #56
	ldm	r1!, {r3, r4, r5}
	stm	r2!, {r3, r4, r5}
	ldm	r1!, {r3, r4, r5}
	stm	r2!, {r3, r4, r5}
	cmp	r0, #3
	bhi	.Lpow_horner_BB10_34
@ %bb.33:
	ldr	r4, [sp, #44]                   @ 4-byte Reload
	b	.Lpow_horner_BB10_37
.Lpow_horner_BB10_34:
	ldr	r4, [sp, #44]                   @ 4-byte Reload
	.inst.n	0x1c64 @ adds	r4, r4, #1
	b	.Lpow_horner_BB10_37
.Lpow_horner_BB10_35:                              @   in Loop: Header=BB10_37 Depth=1
	add	r0, sp, #80
	bl	pow_integer128_square
	.inst.n	0x1e64 @ subs	r4, r4, #1
	mov	r0, r6
	lsrs	r0, r4
	lsls	r0, r0, #31
	beq	.Lpow_horner_BB10_37
@ %bb.36:                               @   in Loop: Header=BB10_37 Depth=1
	add	r0, sp, #80
	add	r1, sp, #56
	bl	pow_integer128_base
.Lpow_horner_BB10_37:                              @ =>This Inner Loop Header: Depth=1
	cmp	r4, #0
	bne	.Lpow_horner_BB10_35
.Lpow_horner_BB10_38:
	ldr	r0, [sp, #40]                   @ 4-byte Reload
	cmp	r0, #0
	bmi	.Lpow_horner_BB10_46
@ %bb.39:
	cmp	r7, #1
	bne	.Lpow_horner_BB10_46
@ %bb.40:
	ldr	r3, [sp, #96]
	ldr	r0, .Lpow_horner_CPI10_13
	adds	r0, r0, r3
	.inst.n	0x1cc0 @ adds	r0, r0, #3
	ldr	r1, .Lpow_horner_CPI10_12
	cmp	r0, r1
	blo	.Lpow_horner_BB10_15
@ %bb.41:
	ldr	r5, [sp, #84]
	ldr	r1, [sp, #80]
	movs	r0, #1
	lsls	r2, r0, #11
	movs	r6, #0
	str	r2, [sp, #32]                   @ 4-byte Spill
	.inst.n	0x1e54 @ subs	r4, r2, #1
	str	r6, [sp, #52]                   @ 4-byte Spill
	sbcs	r6, r6
	ands	r4, r1
	ands	r6, r5
	str	r5, [sp, #44]                   @ 4-byte Spill
	lsrs	r7, r5, #11
	lsls	r2, r0, #10
	ldr	r5, [sp, #100]
	cmp	r5, #0
	bne	.Lpow_horner_BB10_42
	b	.Lpow_horner_BB10_75
.Lpow_horner_BB10_42:
	str	r7, [sp, #24]                   @ 4-byte Spill
	str	r2, [sp, #28]                   @ 4-byte Spill
	mov	r7, r1
	ldr	r1, .Lpow_horner_CPI10_15
	str	r7, [sp, #40]                   @ 4-byte Spill
	ands	r1, r7
	ldr	r7, .Lpow_horner_CPI10_16
	cmp	r1, r7
	bne	.Lpow_horner_BB10_43
	b	.Lpow_horner_BB10_76
.Lpow_horner_BB10_43:
	ldr	r2, [sp, #28]                   @ 4-byte Reload
	cmp	r1, r2
	ldr	r1, [sp, #40]                   @ 4-byte Reload
	ldr	r7, [sp, #24]                   @ 4-byte Reload
	beq	.Lpow_horner_BB10_44
	b	.Lpow_horner_BB10_75
.Lpow_horner_BB10_44:
	ldr	r0, [sp, #92]
	ldr	r7, [sp, #88]
	subs	r5, r5, r7
	ldr	r7, [sp, #52]                   @ 4-byte Reload
	mov	r5, r7
	sbcs	r5, r0
	ldr	r5, .Lpow_horner_CPI10_11
	blo	.Lpow_horner_BB10_45
	b	.Lpow_horner_BB10_16
.Lpow_horner_BB10_45:
	b	.Lpow_horner_BB10_77
.Lpow_horner_BB10_46:
	str	r7, [sp, #12]                   @ 4-byte Spill
	ldr	r0, [sp, #92]
	ldr	r7, [sp, #88]
	orrs	r7, r0
	.inst.n	0x1e78 @ subs	r0, r7, #1
	sbcs	r7, r0
	ldr	r0, [sp, #100]
	cmp	r0, #0
	beq	.Lpow_horner_BB10_48
@ %bb.47:
	movs	r7, #2
.Lpow_horner_BB10_48:
	ldr	r1, [sp, #84]
	ldr	r0, [sp, #80]
	ldr	r6, [sp, #96]
	movs	r2, #1
	str	r2, [sp, #20]                   @ 4-byte Spill
	ldr	r2, [sp, #12]                   @ 4-byte Reload
	cmp	r2, #2
	blo	.Lpow_horner_BB10_59
@ %bb.49:
	str	r7, [sp, #44]                   @ 4-byte Spill
	mov	r5, r0
	mov	r3, r1
.Lpow_horner_BB10_50:                              @ =>This Inner Loop Header: Depth=1
	mov	r4, r2
	movs	r2, #1
	ands	r2, r6
	cmp	r7, #0
	bne	.Lpow_horner_BB10_54
@ %bb.51:                               @   in Loop: Header=BB10_50 Depth=1
	str	r5, [sp, #28]                   @ 4-byte Spill
	mov	r5, r1
	str	r6, [sp, #32]                   @ 4-byte Spill
	ldr	r6, [sp, #52]                   @ 4-byte Reload
	eors	r5, r6
	str	r0, [sp, #24]                   @ 4-byte Spill
	orrs	r5, r0
	ldr	r5, [sp, #20]                   @ 4-byte Reload
	bne	.Lpow_horner_BB10_53
@ %bb.52:                               @   in Loop: Header=BB10_50 Depth=1
	mov	r5, r2
.Lpow_horner_BB10_53:                              @   in Loop: Header=BB10_50 Depth=1
	cmp	r5, #0
	ldr	r6, [sp, #32]                   @ 4-byte Reload
	ldr	r5, [sp, #28]                   @ 4-byte Reload
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	beq	.Lpow_horner_BB10_57
.Lpow_horner_BB10_54:                              @   in Loop: Header=BB10_50 Depth=1
	bl	pow_sqrt64_raw
	mov	r5, r0
	mov	r3, r1
	movs	r0, #3
	muls	r0, r7, r0
	.inst.n	0x1cc0 @ adds	r0, r0, #3
	lsrs	r0, r0, #2
	.inst.n	0x1cc7 @ adds	r7, r0, #3
	asrs	r6, r6, #1
	cmp	r1, #0
	str	r7, [sp, #44]                   @ 4-byte Spill
	bmi	.Lpow_horner_BB10_56
@ %bb.55:                               @   in Loop: Header=BB10_50 Depth=1
	lsrs	r1, r3, #1
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	orrs	r1, r0
	lsrs	r0, r5, #1
	lsls	r2, r3, #31
	adds	r5, r0, r2
	.inst.n	0x1c76 @ adds	r6, r6, #1
	mov	r3, r1
	mov	r0, r5
	b	.Lpow_horner_BB10_58
.Lpow_horner_BB10_56:                              @   in Loop: Header=BB10_50 Depth=1
	mov	r0, r5
	mov	r1, r3
	b	.Lpow_horner_BB10_58
.Lpow_horner_BB10_57:                              @   in Loop: Header=BB10_50 Depth=1
	asrs	r6, r6, #1
	movs	r7, #0
	ldr	r0, [sp, #16]                   @ 4-byte Reload
	ldr	r1, [sp, #52]                   @ 4-byte Reload
.Lpow_horner_BB10_58:                              @   in Loop: Header=BB10_50 Depth=1
	lsrs	r2, r4, #1
	cmp	r4, #3
	bls	.Lpow_horner_BB10_60
	b	.Lpow_horner_BB10_50
.Lpow_horner_BB10_59:
	mov	r5, r0
	mov	r3, r1
	str	r7, [sp, #44]                   @ 4-byte Spill
.Lpow_horner_BB10_60:
	str	r5, [sp, #56]
	ldr	r2, [sp, #44]                   @ 4-byte Reload
	str	r2, [sp, #68]
	str	r3, [sp, #60]
	ldr	r2, .Lpow_horner_CPI10_4
	.inst.n	0x1c52 @ adds	r2, r2, #1
	cmp	r7, r2
	bhi	.Lpow_horner_BB10_62
@ %bb.61:
	movs	r2, #0
	b	.Lpow_horner_BB10_63
.Lpow_horner_BB10_62:
	movs	r2, #1
.Lpow_horner_BB10_63:
	str	r6, [sp, #64]
	ldr	r3, .Lpow_horner_CPI10_2
	adds	r3, r3, r6
	.inst.n	0x1d1b @ adds	r3, r3, #4
	ldr	r4, .Lpow_horner_CPI10_1
	.inst.n	0x1ca4 @ adds	r4, r4, #2
	cmp	r3, r4
	ldr	r3, [sp, #20]                   @ 4-byte Reload
	blo	.Lpow_horner_BB10_65
@ %bb.64:
	mov	r3, r2
.Lpow_horner_BB10_65:
	cmp	r3, #0
	beq	.Lpow_horner_BB10_66
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_66:
	ldr	r2, .Lpow_horner_CPI10_6
	ands	r2, r0
	movs	r3, #1
	str	r7, [sp, #52]                   @ 4-byte Spill
	lsls	r5, r3, #31
	mov	r4, r1
	bics	r4, r5
	orrs	r4, r2
	mov	r7, r0
	mov	r2, r0
	ldr	r5, .Lpow_horner_CPI10_3
	ands	r2, r5
	movs	r5, #255
	adds	r5, #254
	str	r5, [sp, #44]                   @ 4-byte Spill
	adds	r5, r2, r5
	.inst.n	0x1ced @ adds	r5, r5, #3
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	cmp	r5, r0
	ldr	r5, [sp, #52]                   @ 4-byte Reload
	bhi	.Lpow_horner_BB10_68
@ %bb.67:
	movs	r3, #0
.Lpow_horner_BB10_68:
	cmp	r4, #0
	ldr	r4, [sp, #20]                   @ 4-byte Reload
	bne	.Lpow_horner_BB10_70
@ %bb.69:
	mov	r4, r3
.Lpow_horner_BB10_70:
	cmp	r4, #1
	beq	.Lpow_horner_BB10_71
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_71:
	ldr	r3, .Lpow_horner_CPI10_4
	adds	r3, r6, r3
	lsls	r3, r3, #20
	lsrs	r4, r1, #11
	adds	r3, r3, r4
	lsrs	r4, r7, #11
	lsls	r0, r1, #21
	adds	r0, r4, r0
	ldr	r1, [sp, #40]                   @ 4-byte Reload
	cmp	r1, #0
	bmi	.Lpow_horner_BB10_85
@ %bb.72:
	cmp	r5, #0
	bne	.Lpow_horner_BB10_73
	b	.Lpow_horner_BB10_104
.Lpow_horner_BB10_73:
	adds	r1, r2, r5
	mov	r6, r5
	ldr	r5, .Lpow_horner_CPI10_4
	.inst.n	0x1cac @ adds	r4, r5, #2
	cmp	r1, r4
	blo	.Lpow_horner_BB10_74
	b	.Lpow_horner_BB10_107
.Lpow_horner_BB10_74:
	str	r0, [sp, #48]                   @ 4-byte Spill
	b	.Lpow_horner_BB10_110
.Lpow_horner_BB10_75:
	ldr	r5, .Lpow_horner_CPI10_4
	adds	r3, r3, r5
	lsls	r3, r3, #20
	adds	r7, r7, r3
	movs	r3, #0
	subs	r5, r2, r4
	mov	r5, r7
	sbcs	r3, r6
	ldr	r7, [sp, #52]                   @ 4-byte Reload
	bhs	.Lpow_horner_BB10_78
	b	.Lpow_horner_BB10_81
.Lpow_horner_BB10_76:
	rsbs	r2, r5, #0
	ldr	r1, [sp, #52]                   @ 4-byte Reload
	mov	r5, r1
	sbcs	r5, r1
	ldr	r7, [sp, #92]
	ldr	r0, [sp, #88]
	subs	r0, r0, r2
	sbcs	r7, r5
	mov	r7, r1
	ldr	r5, .Lpow_horner_CPI10_0
	ldr	r1, [sp, #40]                   @ 4-byte Reload
	blo	.Lpow_horner_BB10_77
	b	.Lpow_horner_BB10_16
.Lpow_horner_BB10_77:
	ldr	r0, .Lpow_horner_CPI10_4
	adds	r0, r3, r0
	lsls	r0, r0, #20
	ldr	r2, [sp, #24]                   @ 4-byte Reload
	adds	r5, r2, r0
	ldr	r2, [sp, #28]                   @ 4-byte Reload
.Lpow_horner_BB10_78:
	eors	r4, r2
	orrs	r4, r6
	bne	.Lpow_horner_BB10_80
@ %bb.79:
	ldr	r0, [sp, #32]                   @ 4-byte Reload
	ands	r0, r1
	ldr	r3, [sp, #88]
	orrs	r3, r0
	ldr	r0, [sp, #92]
	orrs	r0, r3
	.inst.n	0x1e43 @ subs	r3, r0, #1
	sbcs	r0, r3
	b	.Lpow_horner_BB10_81
.Lpow_horner_BB10_80:
	mov	r0, r7
.Lpow_horner_BB10_81:
	ldr	r2, [sp, #44]                   @ 4-byte Reload
	lsls	r2, r2, #21
	lsrs	r1, r1, #11
	adds	r1, r1, r2
	adds	r0, r1, r0
	str	r0, [sp, #48]                   @ 4-byte Spill
	adcs	r5, r7
	b	.Lpow_horner_BB10_16
	.p2align	2
@ %bb.82:
.Lpow_horner_CPI10_17:
	.long	2146959360                      @ 0x7ff80000
	.p2align	2
@ %bb.83:
.Lpow_horner_CPI10_18:
	.long	4294965250                      @ 0xfffff802
	.p2align	2
@ %bb.84:
.Lpow_horner_CPI10_19:
	.long	4294966269                      @ 0xfffffbfd
	.p2align	1
.Lpow_horner_BB10_85:
	ldr	r5, .Lpow_horner_CPI10_4
	.inst.n	0x1ca9 @ adds	r1, r5, #2
	cmp	r2, r1
	ldr	r1, [sp, #20]                   @ 4-byte Reload
	bhi	.Lpow_horner_BB10_87
@ %bb.86:
	subs	r1, r2, r5
	.inst.n	0x1e89 @ subs	r1, r1, #2
	rsbs	r2, r1, #0
	adcs	r2, r1
	ands	r4, r2
	mov	r1, r4
.Lpow_horner_BB10_87:
	movs	r7, #0
	adds	r2, r0, r1
	adcs	r3, r7
	ldr	r1, .Lpow_horner_CPI10_7
	mov	r0, r7
	bl	__aeabi_ddiv
	mov	r5, r0
	ldr	r0, .Lpow_horner_CPI10_8
	.inst.n	0x1cab @ adds	r3, r5, #2
	mov	r2, r1
	sbcs	r2, r0
	ldr	r0, .Lpow_horner_CPI10_9
	.inst.n	0x1f1b @ subs	r3, r3, #4
	adcs	r0, r2
	bhs	.Lpow_horner_BB10_88
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_88:
	.inst.n	0x1c68 @ adds	r0, r5, #1
	mov	r4, r1
	adcs	r4, r7
	ldr	r6, .Lpow_horner_CPI10_10
	ands	r4, r6
	mvns	r3, r7
	movs	r2, #2
	subs	r0, r2, r0
	mov	r0, r7
	sbcs	r0, r4
	mov	r4, r1
	str	r3, [sp, #40]                   @ 4-byte Spill
	blo	.Lpow_horner_BB10_114
@ %bb.89:
	add	r0, sp, #56
	mov	r2, r5
	mov	r3, r4
	bl	root64_boundary
	cmp	r0, #0
	beq	.Lpow_horner_BB10_112
@ %bb.90:
	bpl	.Lpow_horner_BB10_91
	b	.Lpow_horner_BB10_124
.Lpow_horner_BB10_91:
	movs	r6, #0
	.inst.n	0x1e6a @ subs	r2, r5, #1
	mov	r3, r4
	sbcs	r3, r6
	add	r0, sp, #56
	str	r2, [sp, #48]                   @ 4-byte Spill
	str	r3, [sp, #36]                   @ 4-byte Spill
	bl	root64_boundary
	cmp	r0, #0
	bpl	.Lpow_horner_BB10_92
	b	.Lpow_horner_BB10_129
.Lpow_horner_BB10_92:
	bne	.Lpow_horner_BB10_93
	b	.Lpow_horner_BB10_133
.Lpow_horner_BB10_93:
	.inst.n	0x1eaa @ subs	r2, r5, #2
	mov	r7, r4
	sbcs	r7, r6
	add	r0, sp, #56
	str	r2, [sp, #32]                   @ 4-byte Spill
	mov	r3, r7
	bl	root64_boundary
	cmp	r0, #0
	bpl	.Lpow_horner_BB10_94
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_94:
	beq	.Lpow_horner_BB10_95
	b	.Lpow_horner_BB10_126
.Lpow_horner_BB10_95:
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	str	r1, [sp]
	str	r7, [sp, #4]
	ldr	r0, [sp, #40]                   @ 4-byte Reload
	ands	r0, r1
	ldr	r1, .Lpow_horner_CPI10_10
	ands	r1, r7
	orrs	r1, r0
	.inst.n	0x1e48 @ subs	r0, r1, #1
	sbcs	r1, r0
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	cmp	r2, r0
	bhs	.Lpow_horner_BB10_97
@ %bb.96:
	movs	r6, #1
.Lpow_horner_BB10_97:
	ands	r6, r1
	str	r6, [sp, #8]
	b	.Lpow_horner_BB10_156
	.p2align	2
@ %bb.98:
.Lpow_horner_CPI10_11:
	.long	2146959360                      @ 0x7ff80000
	.p2align	2
@ %bb.99:
.Lpow_horner_CPI10_12:
	.long	4294965250                      @ 0xfffff802
	.p2align	2
@ %bb.100:
.Lpow_horner_CPI10_13:
	.long	4294966269                      @ 0xfffffbfd
	.p2align	2
@ %bb.101:
.Lpow_horner_CPI10_14:
	.long	1022                            @ 0x3fe
	.p2align	2
@ %bb.102:
.Lpow_horner_CPI10_15:
	.long	2047                            @ 0x7ff
	.p2align	2
@ %bb.103:
.Lpow_horner_CPI10_16:
	.long	1023                            @ 0x3ff
	.p2align	1
.Lpow_horner_BB10_104:
	ldr	r5, .Lpow_horner_CPI10_4
	.inst.n	0x1ca9 @ adds	r1, r5, #2
	cmp	r2, r1
	bhi	.Lpow_horner_BB10_106
@ %bb.105:
	subs	r1, r2, r5
	.inst.n	0x1e89 @ subs	r1, r1, #2
	rsbs	r2, r1, #0
	adcs	r2, r1
	ands	r4, r2
	str	r4, [sp, #20]                   @ 4-byte Spill
.Lpow_horner_BB10_106:
	movs	r1, #0
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	adds	r0, r0, r2
	b	.Lpow_horner_BB10_109
.Lpow_horner_BB10_107:
	adds	r1, r5, r6
	.inst.n	0x1c89 @ adds	r1, r1, #2
	cmp	r2, r1
	bls	.Lpow_horner_BB10_111
@ %bb.108:
	movs	r1, #0
	.inst.n	0x1c40 @ adds	r0, r0, #1
.Lpow_horner_BB10_109:
	str	r0, [sp, #48]                   @ 4-byte Spill
	adcs	r3, r1
.Lpow_horner_BB10_110:
	str	r3, [sp, #36]                   @ 4-byte Spill
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_111:
	ldr	r1, [sp, #20]                   @ 4-byte Reload
	str	r1, [sp, #8]
	str	r0, [sp]
	str	r3, [sp, #4]
	add	r0, sp, #80
	movs	r2, #0
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	b	.Lpow_horner_BB10_157
.Lpow_horner_BB10_112:
	mov	r0, r4
	ands	r0, r6
	str	r5, [sp]
	str	r4, [sp, #4]
	orrs	r0, r5
	.inst.n	0x1e41 @ subs	r1, r0, #1
	sbcs	r0, r1
	ldr	r1, [sp, #44]                   @ 4-byte Reload
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	cmp	r2, r1
	blo	.Lpow_horner_BB10_127
@ %bb.113:
	movs	r1, #0
	b	.Lpow_horner_BB10_128
.Lpow_horner_BB10_114:
	add	r0, sp, #56
	mov	r6, r5
	mov	r2, r5
	str	r4, [sp, #52]                   @ 4-byte Spill
	mov	r3, r4
	bl	root64_distance
	mov	r2, r0
	ands	r2, r1
	.inst.n	0x1c52 @ adds	r2, r2, #1
	bne	.Lpow_horner_BB10_115
	b	.Lpow_horner_BB10_155
.Lpow_horner_BB10_115:
	lsrs	r2, r1, #11
	rsbs	r3, r2, #0
	cmp	r0, r3
	bge	.Lpow_horner_BB10_117
@ %bb.116:
	movs	r7, #1
.Lpow_horner_BB10_117:
	cmp	r0, r2
	ble	.Lpow_horner_BB10_119
@ %bb.118:
	ldr	r7, [sp, #20]                   @ 4-byte Reload
.Lpow_horner_BB10_119:
	cmp	r7, #1
	bne	.Lpow_horner_BB10_130
@ %bb.120:
	ldr	r4, .Lpow_horner_CPI10_3
	ands	r1, r4
	cmp	r0, r2
	bgt	.Lpow_horner_BB10_137
@ %bb.121:
	cmp	r0, r3
	bge	.Lpow_horner_BB10_137
@ %bb.122:
	movs	r3, #0
	.inst.n	0x1c74 @ adds	r4, r6, #1
	str	r4, [sp, #48]                   @ 4-byte Spill
	ldr	r4, [sp, #52]                   @ 4-byte Reload
	adcs	r3, r4
	str	r3, [sp, #36]                   @ 4-byte Spill
	adds	r1, r1, r0
	.inst.n	0x1c50 @ adds	r0, r2, #1
	cmp	r1, r0
	ble	.Lpow_horner_BB10_123
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_123:
	mvns	r2, r2
	cmp	r1, r2
	bge	.Lpow_horner_BB10_131
	b	.Lpow_horner_BB10_155
.Lpow_horner_BB10_124:
	movs	r7, #0
	.inst.n	0x1c6a @ adds	r2, r5, #1
	mov	r3, r4
	adcs	r3, r7
	add	r0, sp, #56
	str	r2, [sp, #48]                   @ 4-byte Spill
	str	r3, [sp, #36]                   @ 4-byte Spill
	bl	root64_boundary
	cmp	r0, #0
	ble	.Lpow_horner_BB10_125
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_125:
	beq	.Lpow_horner_BB10_143
.Lpow_horner_BB10_126:
	movs	r0, #0
	str	r0, [sp, #8]
	str	r5, [sp]
	str	r4, [sp, #4]
	b	.Lpow_horner_BB10_156
.Lpow_horner_BB10_127:
	movs	r1, #1
.Lpow_horner_BB10_128:
	ands	r1, r0
	str	r1, [sp, #8]
	b	.Lpow_horner_BB10_156
.Lpow_horner_BB10_129:
	str	r5, [sp, #48]                   @ 4-byte Spill
	str	r4, [sp, #36]                   @ 4-byte Spill
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_130:
	str	r6, [sp, #48]                   @ 4-byte Spill
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	str	r0, [sp, #36]                   @ 4-byte Spill
	mov	r0, r2
.Lpow_horner_BB10_131:
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	str	r2, [sp]
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	str	r1, [sp, #4]
	ldr	r3, [sp, #40]                   @ 4-byte Reload
	ands	r3, r2
	ldr	r6, .Lpow_horner_CPI10_10
	ands	r6, r1
	orrs	r6, r3
	.inst.n	0x1e71 @ subs	r1, r6, #1
	sbcs	r6, r1
	mov	r2, r6
	ldr	r1, [sp, #44]                   @ 4-byte Reload
	.inst.n	0x1cc9 @ adds	r1, r1, #3
	cmp	r0, r1
	blo	.Lpow_horner_BB10_135
@ %bb.132:
	movs	r0, #0
	b	.Lpow_horner_BB10_136
.Lpow_horner_BB10_133:
	ldr	r1, [sp, #48]                   @ 4-byte Reload
	str	r1, [sp]
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	str	r0, [sp, #4]
	ldr	r2, [sp, #40]                   @ 4-byte Reload
	ands	r2, r1
	ldr	r5, .Lpow_horner_CPI10_10
	ands	r5, r0
	orrs	r5, r2
	.inst.n	0x1e68 @ subs	r0, r5, #1
	sbcs	r5, r0
	mov	r1, r5
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	cmp	r2, r0
	blo	.Lpow_horner_BB10_140
@ %bb.134:
	movs	r0, #0
	b	.Lpow_horner_BB10_141
.Lpow_horner_BB10_135:
	movs	r0, #1
.Lpow_horner_BB10_136:
	ands	r0, r2
	b	.Lpow_horner_BB10_142
.Lpow_horner_BB10_137:
	subs	r7, r0, r1
	mvns	r4, r2
	.inst.n	0x1c50 @ adds	r0, r2, #1
	cmp	r7, r0
	bgt	.Lpow_horner_BB10_146
@ %bb.138:
	cmp	r7, r4
	bge	.Lpow_horner_BB10_146
@ %bb.139:
	str	r6, [sp, #48]                   @ 4-byte Spill
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	str	r0, [sp, #36]                   @ 4-byte Spill
	b	.Lpow_horner_BB10_158
.Lpow_horner_BB10_140:
	movs	r0, #1
.Lpow_horner_BB10_141:
	ands	r0, r1
.Lpow_horner_BB10_142:
	str	r0, [sp, #8]
	b	.Lpow_horner_BB10_156
.Lpow_horner_BB10_143:
	ldr	r1, [sp, #48]                   @ 4-byte Reload
	str	r1, [sp]
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	str	r0, [sp, #4]
	ldr	r2, [sp, #40]                   @ 4-byte Reload
	ands	r2, r1
	ldr	r5, .Lpow_horner_CPI10_10
	ands	r5, r0
	orrs	r5, r2
	.inst.n	0x1e68 @ subs	r0, r5, #1
	sbcs	r5, r0
	mov	r1, r5
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	cmp	r2, r0
	bhs	.Lpow_horner_BB10_145
@ %bb.144:
	movs	r7, #1
.Lpow_horner_BB10_145:
	ands	r7, r1
	str	r7, [sp, #8]
	b	.Lpow_horner_BB10_156
.Lpow_horner_BB10_146:
	movs	r3, #0
	.inst.n	0x1e75 @ subs	r5, r6, #1
	str	r5, [sp, #48]                   @ 4-byte Spill
	ldr	r5, [sp, #52]                   @ 4-byte Reload
	sbcs	r5, r3
	str	r5, [sp, #36]                   @ 4-byte Spill
	cmp	r7, r0
	bgt	.Lpow_horner_BB10_148
@ %bb.147:
	cmp	r7, r4
	bge	.Lpow_horner_BB10_131
.Lpow_horner_BB10_148:
	movs	r4, #1
	mvns	r0, r4
	subs	r5, r0, r2
	subs	r1, r7, r1
	.inst.n	0x1c90 @ adds	r0, r2, #2
	cmp	r1, r0
	ldr	r7, [sp, #52]                   @ 4-byte Reload
	mov	r2, r6
	bgt	.Lpow_horner_BB10_150
@ %bb.149:
	cmp	r1, r5
	blt	.Lpow_horner_BB10_158
.Lpow_horner_BB10_150:
	.inst.n	0x1e92 @ subs	r2, r2, #2
	str	r2, [sp, #48]                   @ 4-byte Spill
	mov	r2, r7
	sbcs	r2, r3
	str	r2, [sp, #36]                   @ 4-byte Spill
	cmp	r1, r5
	blt	.Lpow_horner_BB10_152
@ %bb.151:
	mov	r4, r3
.Lpow_horner_BB10_152:
	cmp	r1, r0
	ble	.Lpow_horner_BB10_154
@ %bb.153:
	ldr	r4, [sp, #20]                   @ 4-byte Reload
.Lpow_horner_BB10_154:
	cmp	r4, #1
	bne	.Lpow_horner_BB10_131
.Lpow_horner_BB10_155:
	movs	r0, #0
	str	r0, [sp, #8]
	str	r6, [sp]
	ldr	r0, [sp, #52]                   @ 4-byte Reload
	str	r0, [sp, #4]
.Lpow_horner_BB10_156:
	add	r0, sp, #80
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	ldr	r2, [sp, #20]                   @ 4-byte Reload
.Lpow_horner_BB10_157:
	bl	pow_root128_decide
	str	r0, [sp, #48]                   @ 4-byte Spill
	str	r1, [sp, #36]                   @ 4-byte Spill
.Lpow_horner_BB10_158:
	ldr	r5, [sp, #36]                   @ 4-byte Reload
	b	.Lpow_horner_BB10_16
	.p2align	2
@ %bb.159:
.Lpow_horner_CPI10_0:
	.long	2146959360                      @ 0x7ff80000
.Lpow_horner_CPI10_1:
	.long	4294965250                      @ 0xfffff802
.Lpow_horner_CPI10_2:
	.long	4294966269                      @ 0xfffffbfd
.Lpow_horner_CPI10_3:
	.long	2047                            @ 0x7ff
.Lpow_horner_CPI10_4:
	.long	1022                            @ 0x3fe
.Lpow_horner_CPI10_6:
	.long	4294965248                      @ 0xfffff800
.Lpow_horner_CPI10_7:
	.long	1072693248                      @ 0x3ff00000
.Lpow_horner_CPI10_8:
	.long	2146435071                      @ 0x7fefffff
.Lpow_horner_CPI10_9:
	.long	2145386495                      @ 0x7fdfffff
.Lpow_horner_CPI10_10:
	.long	1048575                         @ 0xfffff
.Lpow_horner_func_end10:
	.size	pow_root128, .Lpow_horner_func_end10-pow_root128
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	2                               @ -- Begin function _ZL10factor_powyjjb
	.type	_ZL10factor_powyjjb,%function
	.code	16
	.thumb_func
_ZL10factor_powyjjb:                    @ @_ZL10factor_powyjjb
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#148
	sub	sp, #148
	mov	r5, r3
	mov	r7, r2
	mov	r2, r0
	movs	r0, #1
	str	r0, [sp, #100]                  @ 4-byte Spill
	lsls	r0, r3
	str	r0, [sp, #72]                   @ 4-byte Spill
	ldr	r0, .Lpow_horner_CPI11_0
	str	r0, [sp, #32]                   @ 4-byte Spill
	movs	r0, #0
	str	r0, [sp, #36]                   @ 4-byte Spill
	ldr	r4, .Lpow_horner_CPI11_1
	ldr	r0, [sp, #168]
	str	r0, [sp, #16]                   @ 4-byte Spill
	cmp	r0, #0
	str	r7, [sp, #96]                   @ 4-byte Spill
	str	r1, [sp, #24]                   @ 4-byte Spill
	str	r2, [sp, #20]                   @ 4-byte Spill
	beq	.Lpow_horner_BB11_17
@ %bb.1:
	add	r0, sp, #112
	mov	r3, r1
	bl	_ZL14factor_inversey
	cmp	r5, #0
	bne	.Lpow_horner_BB11_2
	b	.Lpow_horner_BB11_56
.Lpow_horner_BB11_2:
	movs	r0, #1
	str	r0, [sp, #80]                   @ 4-byte Spill
	lsls	r0, r0, #31
	str	r0, [sp, #84]                   @ 4-byte Spill
	ldr	r5, [sp, #116]
	ldr	r3, [sp, #112]
	movs	r0, #0
	ldr	r1, [sp, #124]
	str	r1, [sp, #108]                  @ 4-byte Spill
	ldr	r4, [sp, #120]
	str	r0, [sp, #68]                   @ 4-byte Spill
	str	r0, [sp, #92]                   @ 4-byte Spill
	ldr	r6, [sp, #72]                   @ 4-byte Reload
.Lpow_horner_BB11_3:                               @ =>This Inner Loop Header: Depth=1
	lsrs	r0, r6, #1
	str	r0, [sp, #104]                  @ 4-byte Spill
	tst	r0, r7
	beq	.Lpow_horner_BB11_8
@ %bb.4:                                @   in Loop: Header=BB11_3 Depth=1
	str	r3, [sp, #88]                   @ 4-byte Spill
	ldr	r0, [sp, #92]                   @ 4-byte Reload
	lsls	r0, r0, #31
	beq	.Lpow_horner_BB11_6
@ %bb.5:                                @   in Loop: Header=BB11_3 Depth=1
	add	r0, sp, #128
	add	r1, sp, #112
	bl	factor64_multiply
	b	.Lpow_horner_BB11_7
.Lpow_horner_BB11_6:                               @   in Loop: Header=BB11_3 Depth=1
	add	r0, sp, #112
	str	r0, [sp, #92]                   @ 4-byte Spill
	add	r1, sp, #128
	str	r4, [sp, #76]                   @ 4-byte Spill
	ldr	r4, [sp, #92]                   @ 4-byte Reload
	ldm	r4!, {r0, r2, r3, r7}
	stm	r1!, {r0, r2, r3, r7}
	ldr	r4, [sp, #76]                   @ 4-byte Reload
	ldr	r7, [sp, #96]                   @ 4-byte Reload
.Lpow_horner_BB11_7:                               @   in Loop: Header=BB11_3 Depth=1
	ldr	r0, [sp, #100]                  @ 4-byte Reload
	str	r0, [sp, #92]                   @ 4-byte Spill
	ldr	r3, [sp, #88]                   @ 4-byte Reload
.Lpow_horner_BB11_8:                               @   in Loop: Header=BB11_3 Depth=1
	cmp	r6, #4
	bhs	.Lpow_horner_BB11_9
	b	.Lpow_horner_BB11_31
.Lpow_horner_BB11_9:                               @   in Loop: Header=BB11_3 Depth=1
	mov	r2, r4
	ldr	r0, [sp, #80]                   @ 4-byte Reload
	ands	r2, r0
	ldr	r6, [sp, #108]                  @ 4-byte Reload
	cmp	r6, #0
	bne	.Lpow_horner_BB11_13
@ %bb.10:                               @   in Loop: Header=BB11_3 Depth=1
	mov	r0, r5
	ldr	r1, [sp, #84]                   @ 4-byte Reload
	eors	r0, r1
	orrs	r0, r3
	ldr	r0, [sp, #100]                  @ 4-byte Reload
	bne	.Lpow_horner_BB11_12
@ %bb.11:                               @   in Loop: Header=BB11_3 Depth=1
	mov	r0, r2
.Lpow_horner_BB11_12:                              @   in Loop: Header=BB11_3 Depth=1
	cmp	r0, #0
	beq	.Lpow_horner_BB11_16
.Lpow_horner_BB11_13:                              @   in Loop: Header=BB11_3 Depth=1
	mov	r0, r3
	mov	r1, r5
	bl	pow_sqrt64_raw
	mov	r3, r0
	mov	r5, r1
	asrs	r4, r4, #1
	str	r4, [sp, #120]
	movs	r0, #3
	muls	r0, r6, r0
	.inst.n	0x1cc0 @ adds	r0, r0, #3
	lsrs	r0, r0, #2
	.inst.n	0x1cc0 @ adds	r0, r0, #3
	str	r0, [sp, #124]
	cmp	r1, #0
	str	r0, [sp, #108]                  @ 4-byte Spill
	bmi	.Lpow_horner_BB11_15
@ %bb.14:                               @   in Loop: Header=BB11_3 Depth=1
	.inst.n	0x1c64 @ adds	r4, r4, #1
	str	r4, [sp, #120]
	lsrs	r0, r5, #1
	ldr	r1, [sp, #84]                   @ 4-byte Reload
	orrs	r0, r1
	lsrs	r1, r3, #1
	lsls	r2, r5, #31
	adds	r3, r1, r2
	mov	r5, r0
.Lpow_horner_BB11_15:                              @   in Loop: Header=BB11_3 Depth=1
	str	r3, [sp, #112]
	str	r5, [sp, #116]
	ldr	r6, [sp, #104]                  @ 4-byte Reload
	b	.Lpow_horner_BB11_3
.Lpow_horner_BB11_16:                              @   in Loop: Header=BB11_3 Depth=1
	asrs	r4, r4, #1
	str	r4, [sp, #120]
	movs	r0, #0
	str	r0, [sp, #108]                  @ 4-byte Spill
	ldr	r6, [sp, #104]                  @ 4-byte Reload
	ldr	r3, [sp, #68]                   @ 4-byte Reload
	ldr	r5, [sp, #84]                   @ 4-byte Reload
	b	.Lpow_horner_BB11_3
.Lpow_horner_BB11_17:
	lsrs	r0, r2, #21
	mov	r3, r2
	mov	r2, r1
	lsls	r1, r1, #11
	adds	r7, r1, r0
	movs	r0, #1
	str	r0, [sp, #108]                  @ 4-byte Spill
	lsls	r0, r0, #31
	str	r0, [sp, #68]                   @ 4-byte Spill
	orrs	r7, r0
	lsrs	r0, r2, #20
	adds	r6, r0, r4
	lsls	r0, r3, #11
	movs	r2, #0
	cmp	r5, #0
	bne	.Lpow_horner_BB11_18
	b	.Lpow_horner_BB11_33
.Lpow_horner_BB11_18:
	str	r2, [sp, #28]                   @ 4-byte Spill
	.inst.n	0x1c72 @ adds	r2, r6, #1
	str	r2, [sp, #40]                   @ 4-byte Spill
	movs	r2, #31
	lsls	r2, r2, #11
	ands	r2, r0
	str	r2, [sp, #60]                   @ 4-byte Spill
	lsrs	r2, r0, #16
	str	r2, [sp, #56]                   @ 4-byte Spill
	lsrs	r2, r7, #16
	str	r2, [sp, #52]                   @ 4-byte Spill
	uxth	r1, r7
	str	r1, [sp, #48]                   @ 4-byte Spill
	lsrs	r2, r7, #24
	.inst.n	0x1c51 @ adds	r1, r2, #1
	str	r1, [sp, #44]                   @ 4-byte Spill
	movs	r5, #0
	movs	r4, #2
	str	r6, [sp, #64]                   @ 4-byte Spill
.Lpow_horner_BB11_19:                              @ =>This Inner Loop Header: Depth=1
	mov	r2, r6
	ldr	r3, [sp, #108]                  @ 4-byte Reload
	ands	r2, r3
	cmp	r5, #0
	bne	.Lpow_horner_BB11_23
@ %bb.20:                               @   in Loop: Header=BB11_19 Depth=1
	mov	r1, r4
	mov	r3, r7
	ldr	r4, [sp, #68]                   @ 4-byte Reload
	eors	r3, r4
	orrs	r3, r0
	ldr	r3, [sp, #100]                  @ 4-byte Reload
	bne	.Lpow_horner_BB11_22
@ %bb.21:                               @   in Loop: Header=BB11_19 Depth=1
	mov	r3, r2
.Lpow_horner_BB11_22:                              @   in Loop: Header=BB11_19 Depth=1
	cmp	r3, #0
	mov	r4, r1
	beq	.Lpow_horner_BB11_25
.Lpow_horner_BB11_23:                              @   in Loop: Header=BB11_19 Depth=1
	mov	r1, r7
	bl	pow_sqrt64_raw
	mov	r7, r1
	movs	r2, #3
	muls	r2, r5, r2
	.inst.n	0x1cd2 @ adds	r2, r2, #3
	lsrs	r2, r2, #2
	.inst.n	0x1cd5 @ adds	r5, r2, #3
	asrs	r6, r6, #1
	cmp	r1, #0
	bmi	.Lpow_horner_BB11_26
@ %bb.24:                               @   in Loop: Header=BB11_19 Depth=1
	lsrs	r2, r7, #1
	ldr	r3, [sp, #68]                   @ 4-byte Reload
	orrs	r2, r3
	lsrs	r0, r0, #1
	lsls	r1, r7, #31
	adds	r0, r0, r1
	.inst.n	0x1c76 @ adds	r6, r6, #1
	mov	r7, r2
	b	.Lpow_horner_BB11_26
.Lpow_horner_BB11_25:                              @   in Loop: Header=BB11_19 Depth=1
	asrs	r6, r6, #1
	movs	r5, #0
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	ldr	r7, [sp, #68]                   @ 4-byte Reload
.Lpow_horner_BB11_26:                              @   in Loop: Header=BB11_19 Depth=1
	ldr	r1, [sp, #96]                   @ 4-byte Reload
	tst	r4, r1
	beq	.Lpow_horner_BB11_30
@ %bb.27:                               @   in Loop: Header=BB11_19 Depth=1
	str	r4, [sp, #88]                   @ 4-byte Spill
	str	r6, [sp, #104]                  @ 4-byte Spill
	str	r5, [sp, #92]                   @ 4-byte Spill
	lsrs	r3, r7, #16
	ldr	r1, [sp, #48]                   @ 4-byte Reload
	mov	r4, r1
	muls	r4, r3, r4
	uxth	r6, r7
	mov	r5, r1
	muls	r5, r6, r5
	str	r5, [sp, #76]                   @ 4-byte Spill
	str	r6, [sp, #80]                   @ 4-byte Spill
	lsrs	r7, r5, #16
	adds	r4, r7, r4
	lsrs	r7, r4, #16
	ldr	r2, [sp, #52]                   @ 4-byte Reload
	mov	r5, r2
	muls	r5, r3, r5
	adds	r5, r7, r5
	uxth	r4, r4
	mov	r7, r2
	muls	r7, r6, r7
	adds	r7, r4, r7
	lsrs	r4, r7, #16
	adds	r4, r5, r4
	str	r4, [sp, #84]                   @ 4-byte Spill
	lsrs	r5, r0, #16
	mov	r6, r1
	muls	r6, r5, r6
	uxth	r0, r0
	muls	r1, r0, r1
	lsrs	r4, r1, #16
	adds	r4, r4, r6
	lsrs	r6, r4, #16
	muls	r5, r2, r5
	adds	r5, r6, r5
	uxth	r4, r4
	muls	r0, r2, r0
	adds	r0, r4, r0
	lsrs	r0, r0, #16
	adds	r0, r5, r0
	lsls	r4, r7, #16
	ldr	r1, [sp, #76]                   @ 4-byte Reload
	uxth	r1, r1
	adds	r4, r4, r1
	movs	r7, #0
	adds	r0, r4, r0
	adcs	r7, r7
	ldr	r5, [sp, #60]                   @ 4-byte Reload
	mov	r4, r5
	muls	r4, r3, r4
	ldr	r1, [sp, #80]                   @ 4-byte Reload
	muls	r5, r1, r5
	lsrs	r5, r5, #16
	adds	r4, r5, r4
	lsrs	r5, r4, #16
	ldr	r6, [sp, #56]                   @ 4-byte Reload
	muls	r3, r6, r3
	adds	r3, r5, r3
	uxth	r4, r4
	muls	r1, r6, r1
	adds	r2, r4, r1
	lsrs	r2, r2, #16
	adds	r2, r3, r2
	adds	r0, r0, r2
	ldr	r1, [sp, #84]                   @ 4-byte Reload
	adcs	r7, r1
	cmp	r7, #0
	ldr	r2, [sp, #64]                   @ 4-byte Reload
	bge	.Lpow_horner_BB11_29
@ %bb.28:                               @   in Loop: Header=BB11_19 Depth=1
	ldr	r2, [sp, #40]                   @ 4-byte Reload
.Lpow_horner_BB11_29:                              @   in Loop: Header=BB11_19 Depth=1
	lsrs	r4, r0, #1
	lsrs	r3, r7, #31
	mov	r5, r3
	adds	r5, #30
	lsrs	r4, r5
	ldr	r5, [sp, #108]                  @ 4-byte Reload
	eors	r3, r5
	lsls	r7, r3
	orrs	r7, r4
	lsls	r0, r3
	ldr	r4, [sp, #92]                   @ 4-byte Reload
	ldr	r1, [sp, #44]                   @ 4-byte Reload
	muls	r4, r1, r4
	adds	r4, #255
	lsrs	r4, r4, #8
	.inst.n	0x1ce5 @ adds	r5, r4, #3
	lsls	r5, r3
	ldr	r6, [sp, #104]                  @ 4-byte Reload
	adds	r6, r6, r2
	ldr	r4, [sp, #88]                   @ 4-byte Reload
.Lpow_horner_BB11_30:                              @   in Loop: Header=BB11_19 Depth=1
	lsls	r4, r4, #1
	ldr	r2, [sp, #72]                   @ 4-byte Reload
	cmp	r2, r4
	blo	.Lpow_horner_BB11_34
	b	.Lpow_horner_BB11_19
.Lpow_horner_BB11_31:
	ldr	r0, [sp, #92]                   @ 4-byte Reload
	lsls	r0, r0, #31
	beq	.Lpow_horner_BB11_56
@ %bb.32:
	ldr	r5, [sp, #140]
	ldr	r6, [sp, #136]
	b	.Lpow_horner_BB11_35
.Lpow_horner_BB11_33:
	mov	r5, r2
.Lpow_horner_BB11_34:
	str	r0, [sp, #128]
	str	r7, [sp, #132]
	ldr	r7, [sp, #96]                   @ 4-byte Reload
.Lpow_horner_BB11_35:
	ldr	r4, .Lpow_horner_CPI11_1
	ldr	r0, .Lpow_horner_CPI11_2
	.inst.n	0x1c41 @ adds	r1, r0, #1
	cmp	r5, r1
	bhi	.Lpow_horner_BB11_37
@ %bb.36:
	movs	r1, #0
	b	.Lpow_horner_BB11_38
.Lpow_horner_BB11_37:
	movs	r1, #1
.Lpow_horner_BB11_38:
	adds	r2, r6, r4
	ldr	r3, .Lpow_horner_CPI11_3
	cmp	r2, r3
	ldr	r2, [sp, #100]                  @ 4-byte Reload
	blo	.Lpow_horner_BB11_40
@ %bb.39:
	mov	r2, r1
.Lpow_horner_BB11_40:
	cmp	r2, #0
	bne	.Lpow_horner_BB11_56
@ %bb.41:
	str	r6, [sp, #104]                  @ 4-byte Spill
	ldr	r1, .Lpow_horner_CPI11_4
	ldr	r2, [sp, #128]
	ands	r1, r2
	movs	r4, #1
	mov	r0, r5
	lsls	r5, r4, #31
	ldr	r3, [sp, #132]
	mov	r6, r3
	bics	r6, r5
	orrs	r6, r1
	ldr	r1, .Lpow_horner_CPI11_5
	ands	r1, r2
	lsls	r5, r4, #9
	adds	r5, r1, r5
	cmp	r5, r0
	mov	r5, r0
	bhi	.Lpow_horner_BB11_43
@ %bb.42:
	movs	r4, #0
.Lpow_horner_BB11_43:
	cmp	r6, #0
	ldr	r6, [sp, #100]                  @ 4-byte Reload
	bne	.Lpow_horner_BB11_45
@ %bb.44:
	mov	r6, r4
.Lpow_horner_BB11_45:
	cmp	r6, #1
	bne	.Lpow_horner_BB11_56
@ %bb.46:
	lsls	r4, r3, #21
	lsrs	r2, r2, #11
	adds	r4, r2, r4
	str	r4, [sp, #36]                   @ 4-byte Spill
	ldr	r0, [sp, #104]                  @ 4-byte Reload
	ldr	r6, .Lpow_horner_CPI11_2
	adds	r4, r0, r6
	mov	r0, r6
	lsls	r4, r4, #20
	lsrs	r3, r3, #11
	adds	r3, r3, r4
	str	r3, [sp, #32]                   @ 4-byte Spill
	cmp	r5, #0
	beq	.Lpow_horner_BB11_50
@ %bb.47:
	adds	r2, r1, r5
	.inst.n	0x1c83 @ adds	r3, r0, #2
	cmp	r2, r3
	blo	.Lpow_horner_BB11_56
@ %bb.48:
	adds	r0, r0, r5
	.inst.n	0x1c80 @ adds	r0, r0, #2
	cmp	r1, r0
	bls	.Lpow_horner_BB11_54
@ %bb.49:
	movs	r0, #0
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	.inst.n	0x1c49 @ adds	r1, r1, #1
	b	.Lpow_horner_BB11_53
.Lpow_horner_BB11_50:
	.inst.n	0x1c83 @ adds	r3, r0, #2
	cmp	r1, r3
	bhi	.Lpow_horner_BB11_52
@ %bb.51:
	subs	r0, r1, r0
	.inst.n	0x1e80 @ subs	r0, r0, #2
	rsbs	r1, r0, #0
	adcs	r1, r0
	ands	r2, r1
	str	r2, [sp, #100]                  @ 4-byte Spill
.Lpow_horner_BB11_52:
	movs	r0, #0
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	ldr	r2, [sp, #100]                  @ 4-byte Reload
	adds	r1, r1, r2
.Lpow_horner_BB11_53:
	str	r1, [sp, #36]                   @ 4-byte Spill
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	adcs	r1, r0
	b	.Lpow_horner_BB11_55
.Lpow_horner_BB11_54:
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	str	r0, [sp, #8]
	ldr	r0, [sp, #16]                   @ 4-byte Reload
	str	r0, [sp]
	ldr	r0, [sp, #32]                   @ 4-byte Reload
	str	r0, [sp, #12]
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r1, [sp, #24]                   @ 4-byte Reload
	mov	r2, r7
	ldr	r3, [sp, #72]                   @ 4-byte Reload
	bl	_ZL13factor_decideyjjbyb
	str	r0, [sp, #36]                   @ 4-byte Spill
.Lpow_horner_BB11_55:
	str	r1, [sp, #32]                   @ 4-byte Spill
.Lpow_horner_BB11_56:
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	ldr	r1, [sp, #32]                   @ 4-byte Reload
	add	sp, #148
	pop	{r4, r5, r6, r7, pc}
	.p2align	2
@ %bb.57:
.Lpow_horner_CPI11_0:
	.long	2146959360                      @ 0x7ff80000
.Lpow_horner_CPI11_1:
	.long	4294966273                      @ 0xfffffc01
.Lpow_horner_CPI11_2:
	.long	1022                            @ 0x3fe
.Lpow_horner_CPI11_3:
	.long	4294965252                      @ 0xfffff804
.Lpow_horner_CPI11_4:
	.long	4294965248                      @ 0xfffff800
.Lpow_horner_CPI11_5:
	.long	2047                            @ 0x7ff
.Lpow_horner_func_end11:
	.size	_ZL10factor_powyjjb, .Lpow_horner_func_end11-_ZL10factor_powyjjb
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	1                               @ -- Begin function _ZL15root128_compareRK13PowInteger128S1_
	.type	_ZL15root128_compareRK13PowInteger128S1_,%function
	.code	16
	.thumb_func
_ZL15root128_compareRK13PowInteger128S1_: @ @_ZL15root128_compareRK13PowInteger128S1_
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#40
	sub	sp, #40
	ldr	r2, [r1, #16]
	ldr	r3, [r0, #16]
	subs	r7, r3, r2
	cmp	r7, #1
	ble	.Lpow_horner_BB12_2
.Lpow_horner_BB12_1:
	movs	r0, #1
	b	.Lpow_horner_BB12_29
.Lpow_horner_BB12_2:
	movs	r3, #0
	mvns	r2, r3
	cmp	r7, r2
	bge	.Lpow_horner_BB12_4
@ %bb.3:
	mov	r0, r2
	b	.Lpow_horner_BB12_29
.Lpow_horner_BB12_4:
	str	r3, [sp]                        @ 4-byte Spill
	str	r2, [sp, #8]                    @ 4-byte Spill
	ldr	r2, [r1, #12]
	str	r2, [sp, #32]                   @ 4-byte Spill
	ldr	r2, [r1, #8]
	str	r2, [sp, #28]                   @ 4-byte Spill
	ldr	r4, [r1, #4]
	ldr	r2, [r1]
	str	r2, [sp, #36]                   @ 4-byte Spill
	ldr	r2, [r0, #12]
	ldr	r5, [r0, #8]
	ldr	r3, [r0, #4]
	ldr	r6, [r0]
	ldr	r1, [r1, #20]
	str	r1, [sp, #12]                   @ 4-byte Spill
	ldr	r0, [r0, #20]
	cmp	r7, #0
	str	r0, [sp, #16]                   @ 4-byte Spill
	bmi	.Lpow_horner_BB12_7
@ %bb.5:
	str	r3, [sp, #4]                    @ 4-byte Spill
	str	r5, [sp, #24]                   @ 4-byte Spill
	cmp	r7, #1
	bne	.Lpow_horner_BB12_8
@ %bb.6:
	ldr	r3, [sp, #36]                   @ 4-byte Reload
	lsrs	r0, r3, #1
	lsls	r1, r4, #31
	adds	r0, r0, r1
	str	r0, [sp, #20]                   @ 4-byte Spill
	lsls	r1, r3, #31
	ldr	r3, [sp, #32]                   @ 4-byte Reload
	lsrs	r7, r3, #1
	adds	r1, r1, r7
	ldr	r0, [sp, #28]                   @ 4-byte Reload
	lsrs	r7, r0, #1
	lsls	r0, r3, #31
	adds	r5, r0, r7
	lsrs	r4, r4, #1
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	lsrs	r0, r0, #1
	.inst.n	0x1c40 @ adds	r0, r0, #1
	str	r0, [sp, #12]                   @ 4-byte Spill
	str	r1, [sp, #32]                   @ 4-byte Spill
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	str	r2, [sp, #20]                   @ 4-byte Spill
	mov	r7, r6
	b	.Lpow_horner_BB12_9
.Lpow_horner_BB12_7:
	lsrs	r0, r6, #1
	lsls	r1, r3, #31
	adds	r7, r0, r1
	lsls	r0, r6, #31
	lsrs	r1, r2, #1
	adds	r0, r0, r1
	str	r0, [sp, #20]                   @ 4-byte Spill
	lsrs	r0, r5, #1
	lsls	r2, r2, #31
	adds	r0, r2, r0
	str	r0, [sp, #24]                   @ 4-byte Spill
	lsrs	r3, r3, #1
	ldr	r0, [sp, #16]                   @ 4-byte Reload
	lsrs	r0, r0, #1
	.inst.n	0x1c40 @ adds	r0, r0, #1
	str	r0, [sp, #16]                   @ 4-byte Spill
	ldr	r5, [sp, #28]                   @ 4-byte Reload
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	b	.Lpow_horner_BB12_10
.Lpow_horner_BB12_8:
	str	r2, [sp, #20]                   @ 4-byte Spill
	mov	r7, r6
	ldr	r5, [sp, #28]                   @ 4-byte Reload
	ldr	r0, [sp, #36]                   @ 4-byte Reload
.Lpow_horner_BB12_9:
	ldr	r3, [sp, #4]                    @ 4-byte Reload
.Lpow_horner_BB12_10:
	mov	r2, r7
	str	r0, [sp, #36]                   @ 4-byte Spill
	eors	r2, r0
	mov	r0, r3
	eors	r0, r4
	orrs	r0, r2
	bne	.Lpow_horner_BB12_16
@ %bb.11:
	ldr	r2, [sp, #32]                   @ 4-byte Reload
	ldr	r6, [sp, #20]                   @ 4-byte Reload
	cmp	r6, r2
	bne	.Lpow_horner_BB12_15
@ %bb.12:
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	adds	r1, r1, r0
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	cmp	r0, r5
	bhs	.Lpow_horner_BB12_27
@ %bb.13:
	subs	r2, r5, r0
	movs	r0, #0
	cmp	r2, r1
	bls	.Lpow_horner_BB12_29
@ %bb.14:
	mvns	r0, r0
	b	.Lpow_horner_BB12_29
.Lpow_horner_BB12_15:
	str	r3, [sp, #4]                    @ 4-byte Spill
	mov	r3, r2
	ldr	r2, [sp, #24]                   @ 4-byte Reload
	eors	r2, r5
	eors	r6, r3
	ldr	r3, [sp, #4]                    @ 4-byte Reload
	orrs	r6, r2
	beq	.Lpow_horner_BB12_28
.Lpow_horner_BB12_16:
	mov	r2, r3
	rsbs	r6, r0, #0
	adcs	r6, r0
	movs	r1, #1
	ldr	r0, [sp, #24]                   @ 4-byte Reload
	str	r5, [sp, #28]                   @ 4-byte Spill
	subs	r0, r0, r5
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	ldr	r3, [sp, #32]                   @ 4-byte Reload
	sbcs	r0, r3
	str	r1, [sp, #4]                    @ 4-byte Spill
	mov	r0, r1
	blo	.Lpow_horner_BB12_18
@ %bb.17:
	ldr	r0, [sp]                        @ 4-byte Reload
.Lpow_horner_BB12_18:
	ldr	r1, [sp, #36]                   @ 4-byte Reload
	subs	r5, r7, r1
	mov	r5, r2
	sbcs	r5, r4
	blo	.Lpow_horner_BB12_21
@ %bb.19:
	ands	r6, r0
	bne	.Lpow_horner_BB12_21
@ %bb.20:
	ldr	r6, [sp, #36]                   @ 4-byte Reload
	str	r4, [sp]                        @ 4-byte Spill
	mov	r0, r7
	mov	r3, r2
	ldr	r2, [sp, #4]                    @ 4-byte Reload
	str	r2, [sp, #8]                    @ 4-byte Spill
	ldr	r7, [sp, #20]                   @ 4-byte Reload
	add	r5, sp, #24
	ldm	r5, {r1, r4, r5}                @ 12-byte Folded Reload
	b	.Lpow_horner_BB12_22
.Lpow_horner_BB12_21:
	mov	r6, r7
	str	r2, [sp]                        @ 4-byte Spill
	ldr	r1, [sp, #28]                   @ 4-byte Reload
	ldr	r7, [sp, #32]                   @ 4-byte Reload
	mov	r3, r4
	ldr	r4, [sp, #24]                   @ 4-byte Reload
	ldr	r0, [sp, #36]                   @ 4-byte Reload
	ldr	r5, [sp, #20]                   @ 4-byte Reload
	ldr	r2, [sp, #4]                    @ 4-byte Reload
.Lpow_horner_BB12_22:
	subs	r6, r0, r6
	ldr	r0, [sp]                        @ 4-byte Reload
	sbcs	r3, r0
	subs	r0, r1, r4
	mov	r0, r7
	sbcs	r0, r5
	blo	.Lpow_horner_BB12_24
@ %bb.23:
	movs	r2, #0
.Lpow_horner_BB12_24:
	eors	r6, r2
	orrs	r6, r3
	bne	.Lpow_horner_BB12_26
@ %bb.25:
	subs	r2, r1, r4
	sbcs	r7, r5
	ldr	r0, [sp, #12]                   @ 4-byte Reload
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	adds	r1, r1, r0
	movs	r0, #0
	subs	r1, r1, r2
	mov	r1, r0
	sbcs	r1, r7
	bhs	.Lpow_horner_BB12_29
.Lpow_horner_BB12_26:
	ldr	r0, [sp, #8]                    @ 4-byte Reload
	b	.Lpow_horner_BB12_29
.Lpow_horner_BB12_27:
	subs	r0, r0, r5
	cmp	r0, r1
	bls	.Lpow_horner_BB12_28
	b	.Lpow_horner_BB12_1
.Lpow_horner_BB12_28:
	movs	r0, #0
.Lpow_horner_BB12_29:
	add	sp, #40
	pop	{r4, r5, r6, r7, pc}
.Lpow_horner_func_end12:
	.size	_ZL15root128_compareRK13PowInteger128S1_, .Lpow_horner_func_end12-_ZL15root128_compareRK13PowInteger128S1_
	.cantunwind
	.fnend
                                        @ -- End function
	.section	.m0_pow_tail_extra,"ax",%progbits
	.p2align	2                               @ -- Begin function _ZL14factor_inversey
	.type	_ZL14factor_inversey,%function
	.code	16
	.thumb_func
_ZL14factor_inversey:                   @ @_ZL14factor_inversey
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#52
	sub	sp, #52
	mov	r5, r3
	str	r0, [sp, #36]                   @ 4-byte Spill
	ldr	r0, .Lpow_horner_CPI13_0
	str	r3, [sp, #44]                   @ 4-byte Spill
	ands	r5, r0
	adds	r0, r5, r0
	.inst.n	0x1c43 @ adds	r3, r0, #1
	lsrs	r0, r5, #11
	ldr	r1, .Lpow_horner_CPI13_1
	orrs	r1, r0
	lsls	r6, r1, #11
	str	r3, [sp, #48]                   @ 4-byte Spill
	subs	r0, r3, r6
	asrs	r3, r0, #31
	eors	r0, r3
	mvns	r2, r2
	mvns	r2, r2
	str	r2, [sp, #28]                   @ 4-byte Spill
	eors	r2, r3
	subs	r4, r2, r3
	sbcs	r0, r3
	movs	r7, #0
	.inst.n	0x1e62 @ subs	r2, r4, #1
	mov	r3, r0
	sbcs	r3, r7
	orrs	r0, r4
	str	r7, [sp, #40]                   @ 4-byte Spill
	mov	r0, r7
	beq	.Lpow_horner_BB13_3
@ %bb.1:
	lsls	r3, r3, #21
	lsrs	r2, r2, #11
	adds	r2, r2, r3
	beq	.Lpow_horner_BB13_3
@ %bb.2:
	mov	r0, r2
	bl	mk61_m0_math_udiv32
.Lpow_horner_BB13_3:
	lsrs	r2, r5, #12
	uxth	r1, r0
	lsrs	r3, r0, #16
	mov	r4, r1
	muls	r4, r3, r4
	muls	r1, r1, r1
	lsrs	r1, r1, #16
	adds	r1, r1, r4
	uxth	r5, r1
	adds	r4, r5, r4
	lsrs	r4, r4, #16
	lsrs	r1, r1, #16
	mov	r5, r3
	muls	r5, r3, r5
	adds	r1, r1, r5
	adds	r4, r1, r4
	movs	r1, #3
	str	r1, [sp, #20]                   @ 4-byte Spill
	muls	r1, r4, r1
	.inst.n	0x1d09 @ adds	r1, r1, #4
	lsrs	r1, r1, #3
	lsls	r1, r1, #1
	muls	r3, r4, r3
	lsrs	r3, r3, #16
	movs	r4, #5
	muls	r4, r3, r4
	adds	r4, #8
	lsrs	r3, r4, #4
	lsls	r3, r3, #1
	rsbs	r5, r3, #0
	rsbs	r4, r0, #0
	ldr	r7, [sp, #48]                   @ 4-byte Reload
	cmp	r7, r6
	blo	.Lpow_horner_BB13_5
@ %bb.4:
	mov	r3, r5
.Lpow_horner_BB13_5:
	blo	.Lpow_horner_BB13_7
@ %bb.6:
	mov	r0, r4
.Lpow_horner_BB13_7:
	adds	r0, r1, r0
	adds	r1, r0, r3
	asrs	r0, r1, #31
	mov	r3, r1
	eors	r3, r0
	subs	r4, r3, r0
	uxth	r5, r4
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	lsrs	r0, r0, #20
	ldr	r3, .Lpow_horner_CPI13_2
	adds	r3, r0, r3
	movs	r0, #1
	str	r3, [sp, #24]                   @ 4-byte Spill
	str	r0, [sp, #32]                   @ 4-byte Spill
	ands	r3, r0
	lsls	r0, r3, #10
	lsls	r2, r2, #2
	adds	r0, r0, r2
	ldr	r2, .Lpow_horner_CPI13_3
	ldr	r0, [r2, r0]
	lsrs	r2, r0, #16
	mov	r6, r2
	muls	r6, r5, r6
	uxth	r7, r0
	muls	r5, r7, r5
	lsrs	r5, r5, #16
	adds	r5, r5, r6
	lsrs	r6, r5, #16
	lsrs	r4, r4, #16
	muls	r2, r4, r2
	adds	r2, r6, r2
	uxth	r5, r5
	muls	r7, r4, r7
	adds	r4, r5, r7
	lsrs	r4, r4, #16
	adds	r2, r2, r4
	.inst.n	0x1c52 @ adds	r2, r2, #1
	lsrs	r4, r2, #1
	adds	r2, r0, r4
	blo	.Lpow_horner_BB13_9
@ %bb.8:
	ldr	r2, [sp, #40]                   @ 4-byte Reload
	mvns	r2, r2
.Lpow_horner_BB13_9:
	cmp	r1, #0
	bpl	.Lpow_horner_BB13_11
@ %bb.10:
	subs	r2, r0, r4
.Lpow_horner_BB13_11:
	uxth	r7, r2
	str	r7, [sp, #16]                   @ 4-byte Spill
	lsrs	r2, r2, #16
	str	r2, [sp, #44]                   @ 4-byte Spill
	mov	r1, r7
	muls	r1, r2, r1
	muls	r7, r7, r7
	lsrs	r0, r7, #16
	adds	r0, r0, r1
	str	r0, [sp, #8]                    @ 4-byte Spill
	uxth	r2, r0
	adds	r0, r2, r1
	str	r0, [sp, #4]                    @ 4-byte Spill
	uxth	r4, r0
	adds	r3, #10
	mov	r5, r3
	str	r3, [sp, #12]                   @ 4-byte Spill
	ldr	r3, [sp, #48]                   @ 4-byte Reload
	lsls	r3, r5
	lsrs	r1, r3, #16
	str	r1, [sp, #48]                   @ 4-byte Spill
	mov	r2, r1
	muls	r2, r4, r2
	uxth	r0, r7
	muls	r1, r0, r1
	movs	r7, #31
	eors	r7, r5
	ldr	r5, [sp, #28]                   @ 4-byte Reload
	lsrs	r6, r5, #1
	lsrs	r6, r7
	orrs	r6, r3
	uxth	r3, r6
	muls	r0, r3, r0
	lsrs	r0, r0, #16
	adds	r0, r0, r1
	lsrs	r1, r0, #16
	adds	r1, r2, r1
	muls	r4, r3, r4
	uxth	r0, r0
	adds	r0, r4, r0
	lsrs	r0, r0, #16
	adds	r0, r1, r0
	str	r0, [sp]                        @ 4-byte Spill
	ldr	r0, [sp, #4]                    @ 4-byte Reload
	lsrs	r0, r0, #16
	ldr	r1, [sp, #8]                    @ 4-byte Reload
	lsrs	r1, r1, #16
	ldr	r2, [sp, #44]                   @ 4-byte Reload
	muls	r2, r2, r2
	adds	r1, r1, r2
	adds	r1, r1, r0
	uxth	r0, r1
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	muls	r2, r0, r2
	mov	r7, r3
	muls	r7, r0, r7
	lsrs	r4, r7, #16
	adds	r2, r4, r2
	str	r2, [sp, #8]                    @ 4-byte Spill
	uxth	r2, r2
	lsrs	r6, r1, #16
	muls	r3, r6, r3
	adds	r1, r2, r3
	str	r1, [sp, #4]                    @ 4-byte Spill
	lsls	r1, r1, #16
	uxth	r2, r7
	adds	r1, r1, r2
	ldr	r2, [sp]                        @ 4-byte Reload
	adds	r1, r2, r1
	str	r1, [sp]                        @ 4-byte Spill
	ldr	r4, [sp, #40]                   @ 4-byte Reload
	mov	r7, r4
	adcs	r7, r4
	ldr	r1, [sp, #12]                   @ 4-byte Reload
	lsls	r5, r1
	lsrs	r1, r5, #16
	mov	r2, r1
	muls	r2, r0, r2
	uxth	r3, r5
	muls	r0, r3, r0
	lsrs	r0, r0, #16
	adds	r0, r0, r2
	lsrs	r2, r0, #16
	muls	r1, r6, r1
	adds	r1, r2, r1
	movs	r2, #63
	lsls	r2, r2, #10
	ands	r2, r0
	muls	r3, r6, r3
	adds	r0, r2, r3
	lsrs	r0, r0, #16
	adds	r0, r1, r0
	ldr	r1, [sp]                        @ 4-byte Reload
	adds	r0, r1, r0
	adcs	r7, r4
	ldr	r1, [sp, #8]                    @ 4-byte Reload
	lsrs	r1, r1, #16
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	muls	r2, r6, r2
	adds	r1, r1, r2
	ldr	r2, [sp, #4]                    @ 4-byte Reload
	lsrs	r2, r2, #16
	adds	r1, r1, r2
	rsbs	r1, r1, #0
	rsbs	r4, r0, #0
	sbcs	r1, r7
	ldr	r0, [sp, #20]                   @ 4-byte Reload
	lsls	r0, r0, #30
	adds	r0, r1, r0
	lsrs	r1, r0, #16
	ldr	r7, [sp, #16]                   @ 4-byte Reload
	mov	r2, r7
	muls	r2, r1, r2
	uxth	r3, r0
	mov	r6, r7
	muls	r6, r3, r6
	lsrs	r5, r6, #16
	adds	r5, r5, r2
	lsrs	r2, r5, #16
	ldr	r0, [sp, #44]                   @ 4-byte Reload
	muls	r1, r0, r1
	adds	r1, r2, r1
	str	r1, [sp, #48]                   @ 4-byte Spill
	uxth	r1, r5
	muls	r3, r0, r3
	adds	r2, r1, r3
	lsrs	r1, r2, #16
	lsrs	r3, r4, #16
	mov	r5, r7
	muls	r5, r3, r5
	uxth	r4, r4
	muls	r7, r4, r7
	lsrs	r7, r7, #16
	adds	r5, r7, r5
	lsrs	r7, r5, #16
	muls	r3, r0, r3
	adds	r3, r7, r3
	uxth	r5, r5
	muls	r0, r4, r0
	adds	r4, r5, r0
	lsrs	r4, r4, #16
	adds	r3, r3, r4
	lsls	r4, r2, #16
	uxth	r0, r6
	adds	r0, r4, r0
	adds	r0, r0, r3
	ldr	r2, [sp, #48]                   @ 4-byte Reload
	adcs	r1, r2
	ldr	r2, [sp, #24]                   @ 4-byte Reload
	asrs	r2, r2, #1
	rsbs	r3, r2, #0
	mvns	r2, r2
	movs	r4, #48
	movs	r5, #24
	cmp	r1, #0
	bge	.Lpow_horner_BB13_13
@ %bb.12:
	mov	r4, r5
.Lpow_horner_BB13_13:
	ldr	r5, [sp, #36]                   @ 4-byte Reload
	str	r4, [r5, #12]
	mov	r4, r5
	bge	.Lpow_horner_BB13_15
@ %bb.14:
	mov	r2, r3
.Lpow_horner_BB13_15:
	str	r2, [r4, #8]
	lsrs	r2, r1, #31
	ldr	r5, [sp, #32]                   @ 4-byte Reload
	eors	r5, r2
	lsrs	r3, r0, #1
	lsls	r0, r5
	str	r0, [r4]
	adds	r2, #30
	lsrs	r3, r2
	lsls	r1, r5
	orrs	r1, r3
	str	r1, [r4, #4]
	add	sp, #52
	pop	{r4, r5, r6, r7, pc}
	.p2align	2
@ %bb.16:
.Lpow_horner_CPI13_0:
	.long	1048575                         @ 0xfffff
.Lpow_horner_CPI13_1:
	.long	513                             @ 0x201
.Lpow_horner_CPI13_2:
	.long	4294966273                      @ 0xfffffc01
.Lpow_horner_CPI13_3:
	.long	factor_rsqrt_seeds
.Lpow_horner_func_end13:
	.size	_ZL14factor_inversey, .Lpow_horner_func_end13-_ZL14factor_inversey
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	2                               @ -- Begin function _ZL13factor_decideyjjbyb
	.type	_ZL13factor_decideyjjbyb,%function
	.code	16
	.thumb_func
_ZL13factor_decideyjjbyb:               @ @_ZL13factor_decideyjjbyb
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, lr}
	push	{r4, r5, r6, r7, lr}
	.pad	#84
	sub	sp, #84
	mov	r6, r3
	mov	r5, r2
	movs	r2, #0
	str	r2, [sp, #68]
	str	r2, [sp, #64]
	str	r2, [sp, #76]
	lsls	r2, r0, #11
	str	r2, [sp, #56]
	lsrs	r2, r1, #20
	ldr	r3, .Lpow_horner_CPI14_0
	adds	r2, r2, r3
	str	r2, [sp, #72]
	lsrs	r0, r0, #21
	lsls	r1, r1, #11
	adds	r0, r1, r0
	movs	r7, #1
	lsls	r1, r7, #31
	orrs	r1, r0
	str	r1, [sp, #60]
	ldr	r1, [sp, #116]
	ldr	r3, [sp, #112]
	ldr	r2, [sp, #104]
	cmp	r5, #1
	beq	.Lpow_horner_BB14_13
@ %bb.1:
	cmp	r5, #7
	bhi	.Lpow_horner_BB14_3
@ %bb.2:
	mov	r0, r5
	b	.Lpow_horner_BB14_4
.Lpow_horner_BB14_3:
	lsrs	r0, r5, #3
.Lpow_horner_BB14_4:
	lsrs	r4, r0, #2
	cmp	r5, #7
	str	r6, [sp, #28]                   @ 4-byte Spill
	str	r7, [sp, #24]                   @ 4-byte Spill
	str	r2, [sp, #20]                   @ 4-byte Spill
	str	r1, [sp, #16]                   @ 4-byte Spill
	str	r3, [sp, #12]                   @ 4-byte Spill
	bls	.Lpow_horner_BB14_6
@ %bb.5:
	.inst.n	0x1ce4 @ adds	r4, r4, #3
.Lpow_horner_BB14_6:
	add	r1, sp, #56
	add	r2, sp, #32
	ldm	r1!, {r3, r6, r7}
	stm	r2!, {r3, r6, r7}
	ldm	r1!, {r3, r6, r7}
	stm	r2!, {r3, r6, r7}
	cmp	r0, #1
	bls	.Lpow_horner_BB14_8
@ %bb.7:
	.inst.n	0x1c64 @ adds	r4, r4, #1
.Lpow_horner_BB14_8:
	ldr	r6, [sp, #28]                   @ 4-byte Reload
	ldr	r7, [sp, #24]                   @ 4-byte Reload
.Lpow_horner_BB14_9:                               @ =>This Inner Loop Header: Depth=1
	cmp	r4, #0
	beq	.Lpow_horner_BB14_12
@ %bb.10:                               @   in Loop: Header=BB14_9 Depth=1
	add	r0, sp, #56
	bl	pow_integer128_square
	.inst.n	0x1e64 @ subs	r4, r4, #1
	mov	r0, r5
	lsrs	r0, r4
	lsls	r0, r0, #31
	beq	.Lpow_horner_BB14_9
@ %bb.11:                               @   in Loop: Header=BB14_9 Depth=1
	add	r0, sp, #56
	add	r1, sp, #32
	bl	pow_integer128_base
	b	.Lpow_horner_BB14_9
.Lpow_horner_BB14_12:
	ldr	r2, [sp, #20]                   @ 4-byte Reload
	ldr	r1, [sp, #16]                   @ 4-byte Reload
	ldr	r3, [sp, #12]                   @ 4-byte Reload
.Lpow_horner_BB14_13:
	str	r7, [sp, #8]
	str	r3, [sp]
	str	r1, [sp, #4]
	add	r0, sp, #56
	mov	r1, r6
	bl	pow_root128_decide
	add	sp, #84
	pop	{r4, r5, r6, r7, pc}
	.p2align	2
@ %bb.14:
.Lpow_horner_CPI14_0:
	.long	4294966273                      @ 0xfffffc01
.Lpow_horner_func_end14:
	.size	_ZL13factor_decideyjjbyb, .Lpow_horner_func_end14-_ZL13factor_decideyjjbyb
	.cantunwind
	.fnend
                                        @ -- End function
	.ident	"Apple clang version 21.0.0 (clang-2100.3.34.2)"
	.section	".note.GNU-stack","",%progbits
	.eabi_attribute	30, 3	@ Tag_ABI_optimization_goals
