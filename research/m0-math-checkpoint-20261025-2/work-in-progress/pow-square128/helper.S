.syntax unified
.cpu cortex-m0plus
.thumb
.section .square128_helper_only,"ax",%progbits
	.globl	mk61_m0_square128_approx_bound    @ -- Begin function mk61_m0_square128_approx_bound
	.p2align	1
	.type	mk61_m0_square128_approx_bound,%function
	.code	16
	.thumb_func
mk61_m0_square128_approx_bound:           @ @mk61_m0_square128_approx_bound
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
	.size	mk61_m0_square128_approx_bound, .Lpow_horner_func_end0-mk61_m0_square128_approx_bound
	.cantunwind
	.fnend
                                        