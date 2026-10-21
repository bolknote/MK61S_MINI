
/Users/bolk/Projects/MK61S_MINI/.build/stm32f411-rom-20261021/resident/fill.o:     file format elf32-littlearm


Disassembly of section .text.mk61_memory_fill_bulk:

00000000 <mk61_memory_fill_bulk>:
   0:	f361 210f 	bfi	r1, r1, #8, #8
   4:	f361 411f 	bfi	r1, r1, #16, #16
   8:	1880      	adds	r0, r0, r2
   a:	f010 0303 	ands.w	r3, r0, #3
   e:	d007      	beq.n	20 <mk61_memory_fill_bulk+0x20>
  10:	1ad2      	subs	r2, r2, r3
  12:	07db      	lsls	r3, r3, #31
  14:	bf48      	it	mi
  16:	f800 1d01 	strbmi.w	r1, [r0, #-1]!
  1a:	bf28      	it	cs
  1c:	f820 1d02 	strhcs.w	r1, [r0, #-2]!
  20:	000b      	movs	r3, r1
  22:	b430      	push	{r4, r5}
  24:	460c      	mov	r4, r1
  26:	460d      	mov	r5, r1
  28:	3a10      	subs	r2, #16
  2a:	bf28      	it	cs
  2c:	e920 003a 	stmdbcs	r0!, {r1, r3, r4, r5}
  30:	d8fa      	bhi.n	28 <mk61_memory_fill_bulk+0x28>
  32:	0752      	lsls	r2, r2, #29
  34:	bf28      	it	cs
  36:	e920 000a 	stmdbcs	r0!, {r1, r3}
  3a:	bf48      	it	mi
  3c:	f840 1d04 	strmi.w	r1, [r0, #-4]!
  40:	0092      	lsls	r2, r2, #2
  42:	bf28      	it	cs
  44:	f820 1d02 	strhcs.w	r1, [r0, #-2]!
  48:	bf48      	it	mi
  4a:	f800 1d01 	strbmi.w	r1, [r0, #-1]!
  4e:	bc30      	pop	{r4, r5}
  50:	4770      	bx	lr
  52:	bf00      	nop
