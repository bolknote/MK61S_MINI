
/Users/bolk/Projects/MK61S_MINI/.build/mk61ai/quant-ablation-v9/arm/linear.o:     file format elf32-littlearm


Disassembly of section .text._ZN6mk61ai18linear_batch_flashEPv:

Disassembly of section .text._ZN6mk61ai17linear_batch_sramEPv:

Disassembly of section .text.mk61ai_q4_a16_dot32:

00000000 <mk61ai_q4_a16_dot32>:
   0:	230f      	movs	r3, #15
   2:	b5f0      	push	{r4, r5, r6, r7, lr}
   4:	001d      	movs	r5, r3
   6:	7802      	ldrb	r2, [r0, #0]
   8:	2600      	movs	r6, #0
   a:	5f8c      	ldrsh	r4, [r1, r6]
   c:	4015      	ands	r5, r2
   e:	3d08      	subs	r5, #8
  10:	436c      	muls	r4, r5
  12:	2602      	movs	r6, #2
  14:	5f8d      	ldrsh	r5, [r1, r6]
  16:	001e      	movs	r6, r3
  18:	0912      	lsrs	r2, r2, #4
  1a:	3a08      	subs	r2, #8
  1c:	436a      	muls	r2, r5
  1e:	18a4      	adds	r4, r4, r2
  20:	7842      	ldrb	r2, [r0, #1]
  22:	2704      	movs	r7, #4
  24:	5fcd      	ldrsh	r5, [r1, r7]
  26:	4016      	ands	r6, r2
  28:	3e08      	subs	r6, #8
  2a:	4375      	muls	r5, r6
  2c:	192d      	adds	r5, r5, r4
  2e:	2606      	movs	r6, #6
  30:	5f8c      	ldrsh	r4, [r1, r6]
  32:	001e      	movs	r6, r3
  34:	0912      	lsrs	r2, r2, #4
  36:	3a08      	subs	r2, #8
  38:	4354      	muls	r4, r2
  3a:	7882      	ldrb	r2, [r0, #2]
  3c:	1964      	adds	r4, r4, r5
  3e:	4016      	ands	r6, r2
  40:	2708      	movs	r7, #8
  42:	5fcd      	ldrsh	r5, [r1, r7]
  44:	3e08      	subs	r6, #8
  46:	4375      	muls	r5, r6
  48:	192d      	adds	r5, r5, r4
  4a:	260a      	movs	r6, #10
  4c:	5f8c      	ldrsh	r4, [r1, r6]
  4e:	001e      	movs	r6, r3
  50:	0912      	lsrs	r2, r2, #4
  52:	3a08      	subs	r2, #8
  54:	4354      	muls	r4, r2
  56:	78c2      	ldrb	r2, [r0, #3]
  58:	1964      	adds	r4, r4, r5
  5a:	4016      	ands	r6, r2
  5c:	270c      	movs	r7, #12
  5e:	5fcd      	ldrsh	r5, [r1, r7]
  60:	3e08      	subs	r6, #8
  62:	4375      	muls	r5, r6
  64:	192d      	adds	r5, r5, r4
  66:	260e      	movs	r6, #14
  68:	5f8c      	ldrsh	r4, [r1, r6]
  6a:	001e      	movs	r6, r3
  6c:	0912      	lsrs	r2, r2, #4
  6e:	3a08      	subs	r2, #8
  70:	4354      	muls	r4, r2
  72:	7902      	ldrb	r2, [r0, #4]
  74:	1964      	adds	r4, r4, r5
  76:	4016      	ands	r6, r2
  78:	2710      	movs	r7, #16
  7a:	5fcd      	ldrsh	r5, [r1, r7]
  7c:	3e08      	subs	r6, #8
  7e:	4375      	muls	r5, r6
  80:	192d      	adds	r5, r5, r4
  82:	2612      	movs	r6, #18
  84:	5f8c      	ldrsh	r4, [r1, r6]
  86:	001e      	movs	r6, r3
  88:	0912      	lsrs	r2, r2, #4
  8a:	3a08      	subs	r2, #8
  8c:	4354      	muls	r4, r2
  8e:	7942      	ldrb	r2, [r0, #5]
  90:	1964      	adds	r4, r4, r5
  92:	4016      	ands	r6, r2
  94:	2714      	movs	r7, #20
  96:	5fcd      	ldrsh	r5, [r1, r7]
  98:	3e08      	subs	r6, #8
  9a:	4375      	muls	r5, r6
  9c:	192d      	adds	r5, r5, r4
  9e:	2616      	movs	r6, #22
  a0:	5f8c      	ldrsh	r4, [r1, r6]
  a2:	001e      	movs	r6, r3
  a4:	0912      	lsrs	r2, r2, #4
  a6:	3a08      	subs	r2, #8
  a8:	4354      	muls	r4, r2
  aa:	7982      	ldrb	r2, [r0, #6]
  ac:	1964      	adds	r4, r4, r5
  ae:	4016      	ands	r6, r2
  b0:	2718      	movs	r7, #24
  b2:	5fcd      	ldrsh	r5, [r1, r7]
  b4:	3e08      	subs	r6, #8
  b6:	4375      	muls	r5, r6
  b8:	192d      	adds	r5, r5, r4
  ba:	261a      	movs	r6, #26
  bc:	5f8c      	ldrsh	r4, [r1, r6]
  be:	001e      	movs	r6, r3
  c0:	0912      	lsrs	r2, r2, #4
  c2:	3a08      	subs	r2, #8
  c4:	4354      	muls	r4, r2
  c6:	79c2      	ldrb	r2, [r0, #7]
  c8:	1964      	adds	r4, r4, r5
  ca:	4016      	ands	r6, r2
  cc:	271c      	movs	r7, #28
  ce:	5fcd      	ldrsh	r5, [r1, r7]
  d0:	3e08      	subs	r6, #8
  d2:	4375      	muls	r5, r6
  d4:	192d      	adds	r5, r5, r4
  d6:	261e      	movs	r6, #30
  d8:	5f8c      	ldrsh	r4, [r1, r6]
  da:	001e      	movs	r6, r3
  dc:	0912      	lsrs	r2, r2, #4
  de:	3a08      	subs	r2, #8
  e0:	4354      	muls	r4, r2
  e2:	7a02      	ldrb	r2, [r0, #8]
  e4:	1964      	adds	r4, r4, r5
  e6:	4016      	ands	r6, r2
  e8:	2720      	movs	r7, #32
  ea:	5fcd      	ldrsh	r5, [r1, r7]
  ec:	3e08      	subs	r6, #8
  ee:	4375      	muls	r5, r6
  f0:	192d      	adds	r5, r5, r4
  f2:	2622      	movs	r6, #34	@ 0x22
  f4:	5f8c      	ldrsh	r4, [r1, r6]
  f6:	001e      	movs	r6, r3
  f8:	0912      	lsrs	r2, r2, #4
  fa:	3a08      	subs	r2, #8
  fc:	4354      	muls	r4, r2
  fe:	7a42      	ldrb	r2, [r0, #9]
 100:	1964      	adds	r4, r4, r5
 102:	4016      	ands	r6, r2
 104:	2724      	movs	r7, #36	@ 0x24
 106:	5fcd      	ldrsh	r5, [r1, r7]
 108:	3e08      	subs	r6, #8
 10a:	4375      	muls	r5, r6
 10c:	192d      	adds	r5, r5, r4
 10e:	2626      	movs	r6, #38	@ 0x26
 110:	5f8c      	ldrsh	r4, [r1, r6]
 112:	001e      	movs	r6, r3
 114:	0912      	lsrs	r2, r2, #4
 116:	3a08      	subs	r2, #8
 118:	4354      	muls	r4, r2
 11a:	7a82      	ldrb	r2, [r0, #10]
 11c:	1964      	adds	r4, r4, r5
 11e:	4016      	ands	r6, r2
 120:	2728      	movs	r7, #40	@ 0x28
 122:	5fcd      	ldrsh	r5, [r1, r7]
 124:	3e08      	subs	r6, #8
 126:	4375      	muls	r5, r6
 128:	192d      	adds	r5, r5, r4
 12a:	262a      	movs	r6, #42	@ 0x2a
 12c:	5f8c      	ldrsh	r4, [r1, r6]
 12e:	001e      	movs	r6, r3
 130:	0912      	lsrs	r2, r2, #4
 132:	3a08      	subs	r2, #8
 134:	4354      	muls	r4, r2
 136:	7ac2      	ldrb	r2, [r0, #11]
 138:	1964      	adds	r4, r4, r5
 13a:	4016      	ands	r6, r2
 13c:	272c      	movs	r7, #44	@ 0x2c
 13e:	5fcd      	ldrsh	r5, [r1, r7]
 140:	3e08      	subs	r6, #8
 142:	4375      	muls	r5, r6
 144:	192d      	adds	r5, r5, r4
 146:	262e      	movs	r6, #46	@ 0x2e
 148:	5f8c      	ldrsh	r4, [r1, r6]
 14a:	001e      	movs	r6, r3
 14c:	0912      	lsrs	r2, r2, #4
 14e:	3a08      	subs	r2, #8
 150:	4354      	muls	r4, r2
 152:	7b02      	ldrb	r2, [r0, #12]
 154:	1964      	adds	r4, r4, r5
 156:	4016      	ands	r6, r2
 158:	2730      	movs	r7, #48	@ 0x30
 15a:	5fcd      	ldrsh	r5, [r1, r7]
 15c:	3e08      	subs	r6, #8
 15e:	4375      	muls	r5, r6
 160:	192d      	adds	r5, r5, r4
 162:	2632      	movs	r6, #50	@ 0x32
 164:	5f8c      	ldrsh	r4, [r1, r6]
 166:	001e      	movs	r6, r3
 168:	0912      	lsrs	r2, r2, #4
 16a:	3a08      	subs	r2, #8
 16c:	4354      	muls	r4, r2
 16e:	7b42      	ldrb	r2, [r0, #13]
 170:	1964      	adds	r4, r4, r5
 172:	4016      	ands	r6, r2
 174:	2734      	movs	r7, #52	@ 0x34
 176:	5fcd      	ldrsh	r5, [r1, r7]
 178:	3e08      	subs	r6, #8
 17a:	4375      	muls	r5, r6
 17c:	192d      	adds	r5, r5, r4
 17e:	2636      	movs	r6, #54	@ 0x36
 180:	5f8c      	ldrsh	r4, [r1, r6]
 182:	001e      	movs	r6, r3
 184:	0912      	lsrs	r2, r2, #4
 186:	3a08      	subs	r2, #8
 188:	4354      	muls	r4, r2
 18a:	7b82      	ldrb	r2, [r0, #14]
 18c:	1964      	adds	r4, r4, r5
 18e:	4016      	ands	r6, r2
 190:	2738      	movs	r7, #56	@ 0x38
 192:	5fcd      	ldrsh	r5, [r1, r7]
 194:	3e08      	subs	r6, #8
 196:	4375      	muls	r5, r6
 198:	0912      	lsrs	r2, r2, #4
 19a:	192d      	adds	r5, r5, r4
 19c:	263a      	movs	r6, #58	@ 0x3a
 19e:	5f8c      	ldrsh	r4, [r1, r6]
 1a0:	3a08      	subs	r2, #8
 1a2:	4354      	muls	r4, r2
 1a4:	7bc2      	ldrb	r2, [r0, #15]
 1a6:	1964      	adds	r4, r4, r5
 1a8:	4013      	ands	r3, r2
 1aa:	253c      	movs	r5, #60	@ 0x3c
 1ac:	5f48      	ldrsh	r0, [r1, r5]
 1ae:	3b08      	subs	r3, #8
 1b0:	4343      	muls	r3, r0
 1b2:	0912      	lsrs	r2, r2, #4
 1b4:	203e      	movs	r0, #62	@ 0x3e
 1b6:	5e08      	ldrsh	r0, [r1, r0]
 1b8:	3a08      	subs	r2, #8
 1ba:	4350      	muls	r0, r2
 1bc:	191b      	adds	r3, r3, r4
 1be:	18c0      	adds	r0, r0, r3
 1c0:	bdf0      	pop	{r4, r5, r6, r7, pc}

Disassembly of section .text.mk61ai_q4_a8_dot32:
