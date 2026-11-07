
.build/mk61ai/swar-v5/swar_probe.o:     file format elf32-littlearm


Disassembly of section .text:

00000000 <swar_q4_int8_32>:
   0:	b5f0      	push	{r4, r5, r6, r7, lr}
   2:	464f      	mov	r7, r9
   4:	4646      	mov	r6, r8
   6:	46d6      	mov	lr, sl
   8:	b5c0      	push	{r6, r7, lr}
   a:	6807      	ldr	r7, [r0, #0]
   c:	6886      	ldr	r6, [r0, #8]
   e:	68c5      	ldr	r5, [r0, #12]
  10:	6843      	ldr	r3, [r0, #4]
  12:	0038      	movs	r0, r7
  14:	4c3c      	ldr	r4, [pc, #240]	@ (108 <swar_q4_int8_32+0x108>)
  16:	4692      	mov	sl, r2
  18:	4020      	ands	r0, r4
  1a:	4684      	mov	ip, r0
  1c:	4662      	mov	r2, ip
  1e:	6808      	ldr	r0, [r1, #0]
  20:	4699      	mov	r9, r3
  22:	4350      	muls	r0, r2
  24:	001a      	movs	r2, r3
  26:	4022      	ands	r2, r4
  28:	4690      	mov	r8, r2
  2a:	690a      	ldr	r2, [r1, #16]
  2c:	4694      	mov	ip, r2
  2e:	4642      	mov	r2, r8
  30:	4663      	mov	r3, ip
  32:	435a      	muls	r2, r3
  34:	2380      	movs	r3, #128	@ 0x80
  36:	4694      	mov	ip, r2
  38:	021b      	lsls	r3, r3, #8
  3a:	4460      	add	r0, ip
  3c:	469c      	mov	ip, r3
  3e:	093b      	lsrs	r3, r7, #4
  40:	001a      	movs	r2, r3
  42:	684b      	ldr	r3, [r1, #4]
  44:	4022      	ands	r2, r4
  46:	435a      	muls	r2, r3
  48:	0a3b      	lsrs	r3, r7, #8
  4a:	4460      	add	r0, ip
  4c:	4694      	mov	ip, r2
  4e:	001a      	movs	r2, r3
  50:	688b      	ldr	r3, [r1, #8]
  52:	4022      	ands	r2, r4
  54:	435a      	muls	r2, r3
  56:	0b3f      	lsrs	r7, r7, #12
  58:	68cb      	ldr	r3, [r1, #12]
  5a:	4460      	add	r0, ip
  5c:	4027      	ands	r7, r4
  5e:	4694      	mov	ip, r2
  60:	435f      	muls	r7, r3
  62:	464b      	mov	r3, r9
  64:	4460      	add	r0, ip
  66:	19c0      	adds	r0, r0, r7
  68:	091f      	lsrs	r7, r3, #4
  6a:	4027      	ands	r7, r4
  6c:	46bc      	mov	ip, r7
  6e:	4663      	mov	r3, ip
  70:	694f      	ldr	r7, [r1, #20]
  72:	002a      	movs	r2, r5
  74:	435f      	muls	r7, r3
  76:	464b      	mov	r3, r9
  78:	19c0      	adds	r0, r0, r7
  7a:	0a1f      	lsrs	r7, r3, #8
  7c:	4027      	ands	r7, r4
  7e:	46bc      	mov	ip, r7
  80:	4663      	mov	r3, ip
  82:	698f      	ldr	r7, [r1, #24]
  84:	4022      	ands	r2, r4
  86:	435f      	muls	r7, r3
  88:	464b      	mov	r3, r9
  8a:	19c0      	adds	r0, r0, r7
  8c:	0b1b      	lsrs	r3, r3, #12
  8e:	69cf      	ldr	r7, [r1, #28]
  90:	4023      	ands	r3, r4
  92:	437b      	muls	r3, r7
  94:	0037      	movs	r7, r6
  96:	18c0      	adds	r0, r0, r3
  98:	6a0b      	ldr	r3, [r1, #32]
  9a:	4027      	ands	r7, r4
  9c:	437b      	muls	r3, r7
  9e:	6b0f      	ldr	r7, [r1, #48]	@ 0x30
  a0:	1400      	asrs	r0, r0, #16
  a2:	4357      	muls	r7, r2
  a4:	2280      	movs	r2, #128	@ 0x80
  a6:	0212      	lsls	r2, r2, #8
  a8:	4694      	mov	ip, r2
  aa:	19db      	adds	r3, r3, r7
  ac:	0937      	lsrs	r7, r6, #4
  ae:	4027      	ands	r7, r4
  b0:	4463      	add	r3, ip
  b2:	46bc      	mov	ip, r7
  b4:	4662      	mov	r2, ip
  b6:	6a4f      	ldr	r7, [r1, #36]	@ 0x24
  b8:	4357      	muls	r7, r2
  ba:	19db      	adds	r3, r3, r7
  bc:	0a37      	lsrs	r7, r6, #8
  be:	4027      	ands	r7, r4
  c0:	46bc      	mov	ip, r7
  c2:	4662      	mov	r2, ip
  c4:	6a8f      	ldr	r7, [r1, #40]	@ 0x28
  c6:	0b36      	lsrs	r6, r6, #12
  c8:	4357      	muls	r7, r2
  ca:	19db      	adds	r3, r3, r7
  cc:	6acf      	ldr	r7, [r1, #44]	@ 0x2c
  ce:	4026      	ands	r6, r4
  d0:	437e      	muls	r6, r7
  d2:	092f      	lsrs	r7, r5, #4
  d4:	199b      	adds	r3, r3, r6
  d6:	6b4e      	ldr	r6, [r1, #52]	@ 0x34
  d8:	4027      	ands	r7, r4
  da:	437e      	muls	r6, r7
  dc:	0a2f      	lsrs	r7, r5, #8
  de:	199b      	adds	r3, r3, r6
  e0:	6b8e      	ldr	r6, [r1, #56]	@ 0x38
  e2:	4027      	ands	r7, r4
  e4:	6bc9      	ldr	r1, [r1, #60]	@ 0x3c
  e6:	0b2d      	lsrs	r5, r5, #12
  e8:	437e      	muls	r6, r7
  ea:	4025      	ands	r5, r4
  ec:	4369      	muls	r1, r5
  ee:	199b      	adds	r3, r3, r6
  f0:	185b      	adds	r3, r3, r1
  f2:	141b      	asrs	r3, r3, #16
  f4:	18c0      	adds	r0, r0, r3
  f6:	4653      	mov	r3, sl
  f8:	00da      	lsls	r2, r3, #3
  fa:	1a80      	subs	r0, r0, r2
  fc:	bce0      	pop	{r5, r6, r7}
  fe:	46ba      	mov	sl, r7
 100:	46b1      	mov	r9, r6
 102:	46a8      	mov	r8, r5
 104:	bdf0      	pop	{r4, r5, r6, r7, pc}
 106:	46c0      	nop			@ (mov r8, r8)
 108:	000f000f 	.word	0x000f000f
