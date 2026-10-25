.syntax unified
.cpu cortex-m0plus
.thumb
.global _ZL16root128_boundaryRK13PowInteger128jby
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
	bl	mk61_m0_bound80_old_compare
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
