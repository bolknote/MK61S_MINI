.syntax unified
.cpu cortex-m0plus
.thumb

.section .unit_multiply,"ax",%progbits
.p2align 2
.global pow_integer128_multiply
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
                                        
.section .unit_compare,"ax",%progbits
.p2align 2
.global _ZL15root128_compareRK13PowInteger128S1_
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
                                        