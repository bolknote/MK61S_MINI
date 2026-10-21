
/Users/bolk/Projects/MK61S_MINI/.build/stm32f411-rom-20261021/flash-experiment/payload.elf:     file format elf32-littlearm


Disassembly of section .text:

08062000 <full_rom>:
 8062000:	b14a      	cbz	r2, 8062016 <full_rom+0x16>
 8062002:	2a03      	cmp	r2, #3
 8062004:	d801      	bhi.n	806200a <full_rom+0xa>
 8062006:	f7a6 bc53 	b.w	80088b0 <*ABS*0x80088b0>
 806200a:	2a0f      	cmp	r2, #15
 806200c:	d801      	bhi.n	8062012 <full_rom+0x12>
 806200e:	f7a6 bc57 	b.w	80088c0 <*ABS*0x80088c0>
 8062012:	f000 b805 	b.w	8062020 <bulk_rom>
 8062016:	4770      	bx	lr
 8062018:	f3af 8000 	nop.w
 806201c:	f3af 8000 	nop.w

08062020 <bulk_rom>:
 8062020:	4613      	mov	r3, r2
 8062022:	460a      	mov	r2, r1
 8062024:	4619      	mov	r1, r3
 8062026:	4b01      	ldr	r3, [pc, #4]	@ (806202c <bulk_rom+0xc>)
 8062028:	4718      	bx	r3
 806202a:	bf00      	nop
 806202c:	1fff3bd5 	.word	0x1fff3bd5

08062030 <full_style>:
 8062030:	b14a      	cbz	r2, 8062046 <full_style+0x16>
 8062032:	2a03      	cmp	r2, #3
 8062034:	d801      	bhi.n	806203a <full_style+0xa>
 8062036:	f7a6 bc3b 	b.w	80088b0 <*ABS*0x80088b0>
 806203a:	2a0f      	cmp	r2, #15
 806203c:	d801      	bhi.n	8062042 <full_style+0x12>
 806203e:	f7a6 bc3f 	b.w	80088c0 <*ABS*0x80088c0>
 8062042:	f000 b805 	b.w	8062050 <bulk_style>
 8062046:	4770      	bx	lr
 8062048:	f3af 8000 	nop.w
 806204c:	f3af 8000 	nop.w

08062050 <bulk_style>:
 8062050:	210ff361 	.word	0x210ff361
 8062054:	411ff361 	.word	0x411ff361
 8062058:	f0101880 	.word	0xf0101880
 806205c:	d0070303 	.word	0xd0070303
 8062060:	07db1ad2 	.word	0x07db1ad2
 8062064:	f800bf48 	.word	0xf800bf48
 8062068:	bf281d01 	.word	0xbf281d01
 806206c:	1d02f820 	.word	0x1d02f820
 8062070:	b430000b 	.word	0xb430000b
 8062074:	460d460c 	.word	0x460d460c
 8062078:	bf283a10 	.word	0xbf283a10
 806207c:	003ae920 	.word	0x003ae920
 8062080:	0752d8fa 	.word	0x0752d8fa
 8062084:	e920bf28 	.word	0xe920bf28
 8062088:	bf48000a 	.word	0xbf48000a
 806208c:	1d04f840 	.word	0x1d04f840
 8062090:	bf280092 	.word	0xbf280092
 8062094:	1d02f820 	.word	0x1d02f820
 8062098:	f800bf48 	.word	0xf800bf48
 806209c:	bc301d01 	.word	0xbc301d01
 80620a0:	4770      	.short	0x4770
 80620a2:	bf00      	nop
 80620a4:	f3af 8000 	nop.w
 80620a8:	f3af 8000 	nop.w
 80620ac:	f3af 8000 	nop.w

080620b0 <full_edges>:
 80620b0:	b14a      	cbz	r2, 80620c6 <full_edges+0x16>
 80620b2:	2a03      	cmp	r2, #3
 80620b4:	d801      	bhi.n	80620ba <full_edges+0xa>
 80620b6:	f7a6 bbfb 	b.w	80088b0 <*ABS*0x80088b0>
 80620ba:	2a0f      	cmp	r2, #15
 80620bc:	d801      	bhi.n	80620c2 <full_edges+0x12>
 80620be:	f7a6 bbff 	b.w	80088c0 <*ABS*0x80088c0>
 80620c2:	f000 b805 	b.w	80620d0 <bulk_edges>
 80620c6:	4770      	bx	lr
 80620c8:	f3af 8000 	nop.w
 80620cc:	f3af 8000 	nop.w

080620d0 <bulk_edges>:
 80620d0:	210ff361 	.word	0x210ff361
 80620d4:	411ff361 	.word	0x411ff361
 80620d8:	60014684 	.word	0x60014684
 80620dc:	f8401880 	.word	0xf8401880
 80620e0:	f0201c04 	.word	0xf0201c04
 80620e4:	eba00003 	.word	0xeba00003
 80620e8:	000b020c 	.word	0x000b020c
 80620ec:	460cb430 	.word	0x460cb430
 80620f0:	3a10460d 	.word	0x3a10460d
 80620f4:	e920bf28 	.word	0xe920bf28
 80620f8:	d8fa003a 	.word	0xd8fa003a
 80620fc:	bf280752 	.word	0xbf280752
 8062100:	000ae920 	.word	0x000ae920
 8062104:	f840bf48 	.word	0xf840bf48
 8062108:	46601d04 	.word	0x46601d04
 806210c:	4770bc30 	.word	0x4770bc30

08062110 <full_loop>:
 8062110:	b14a      	cbz	r2, 8062126 <full_loop+0x16>
 8062112:	2a03      	cmp	r2, #3
 8062114:	d801      	bhi.n	806211a <full_loop+0xa>
 8062116:	f7a6 bbcb 	b.w	80088b0 <*ABS*0x80088b0>
 806211a:	2a0f      	cmp	r2, #15
 806211c:	d801      	bhi.n	8062122 <full_loop+0x12>
 806211e:	f7a6 bbcf 	b.w	80088c0 <*ABS*0x80088c0>
 8062122:	f000 b805 	b.w	8062130 <bulk_loop>
 8062126:	4770      	bx	lr
 8062128:	f3af 8000 	nop.w
 806212c:	f3af 8000 	nop.w

08062130 <bulk_loop>:
 8062130:	210ff361 	.word	0x210ff361
 8062134:	411ff361 	.word	0x411ff361
 8062138:	60014684 	.word	0x60014684
 806213c:	f8401880 	.word	0xf8401880
 8062140:	f0201c04 	.word	0xf0201c04
 8062144:	eba00003 	.word	0xeba00003
 8062148:	000b020c 	.word	0x000b020c
 806214c:	460cb430 	.word	0x460cb430
 8062150:	3a10460d 	.word	0x3a10460d
 8062154:	e920d303 	.word	0xe920d303
 8062158:	3a10003a 	.word	0x3a10003a
 806215c:	0752d2fb 	.word	0x0752d2fb
 8062160:	e920bf28 	.word	0xe920bf28
 8062164:	bf48000a 	.word	0xbf48000a
 8062168:	1d04f840 	.word	0x1d04f840
 806216c:	bc304660 	.word	0xbc304660
 8062170:	4770      	.short	0x4770
 8062172:	bf00      	nop
 8062174:	f3af 8000 	nop.w
 8062178:	f3af 8000 	nop.w
 806217c:	f3af 8000 	nop.w

08062180 <full_style4>:
 8062180:	b14a      	cbz	r2, 8062196 <full_style4+0x16>
 8062182:	2a03      	cmp	r2, #3
 8062184:	d801      	bhi.n	806218a <full_style4+0xa>
 8062186:	f7a6 bb93 	b.w	80088b0 <*ABS*0x80088b0>
 806218a:	2a0f      	cmp	r2, #15
 806218c:	d801      	bhi.n	8062192 <full_style4+0x12>
 806218e:	f7a6 bb97 	b.w	80088c0 <*ABS*0x80088c0>
 8062192:	f000 b807 	b.w	80621a4 <bulk_style4>
 8062196:	4770      	bx	lr
 8062198:	f3af 8000 	nop.w
 806219c:	f3af 8000 	nop.w
 80621a0:	00000000 	.word	0x00000000

080621a4 <bulk_style4>:
 80621a4:	210ff361 	.word	0x210ff361
 80621a8:	411ff361 	.word	0x411ff361
 80621ac:	f0101880 	.word	0xf0101880
 80621b0:	d0070303 	.word	0xd0070303
 80621b4:	07db1ad2 	.word	0x07db1ad2
 80621b8:	f800bf48 	.word	0xf800bf48
 80621bc:	bf281d01 	.word	0xbf281d01
 80621c0:	1d02f820 	.word	0x1d02f820
 80621c4:	b430000b 	.word	0xb430000b
 80621c8:	460d460c 	.word	0x460d460c
 80621cc:	bf283a10 	.word	0xbf283a10
 80621d0:	003ae920 	.word	0x003ae920
 80621d4:	0752d8fa 	.word	0x0752d8fa
 80621d8:	e920bf28 	.word	0xe920bf28
 80621dc:	bf48000a 	.word	0xbf48000a
 80621e0:	1d04f840 	.word	0x1d04f840
 80621e4:	bf280092 	.word	0xbf280092
 80621e8:	1d02f820 	.word	0x1d02f820
 80621ec:	f800bf48 	.word	0xf800bf48
 80621f0:	bc301d01 	.word	0xbc301d01
 80621f4:	4770      	.short	0x4770
 80621f6:	bf00      	nop
 80621f8:	f3af 8000 	nop.w
 80621fc:	f3af 8000 	nop.w

08062200 <full_edges4>:
 8062200:	b14a      	cbz	r2, 8062216 <full_edges4+0x16>
 8062202:	2a03      	cmp	r2, #3
 8062204:	d801      	bhi.n	806220a <full_edges4+0xa>
 8062206:	f7a6 bb53 	b.w	80088b0 <*ABS*0x80088b0>
 806220a:	2a0f      	cmp	r2, #15
 806220c:	d801      	bhi.n	8062212 <full_edges4+0x12>
 806220e:	f7a6 bb57 	b.w	80088c0 <*ABS*0x80088c0>
 8062212:	f000 b807 	b.w	8062224 <bulk_edges4>
 8062216:	4770      	bx	lr
 8062218:	f3af 8000 	nop.w
 806221c:	f3af 8000 	nop.w
 8062220:	00000000 	.word	0x00000000

08062224 <bulk_edges4>:
 8062224:	210ff361 	.word	0x210ff361
 8062228:	411ff361 	.word	0x411ff361
 806222c:	60014684 	.word	0x60014684
 8062230:	f8401880 	.word	0xf8401880
 8062234:	f0201c04 	.word	0xf0201c04
 8062238:	eba00003 	.word	0xeba00003
 806223c:	000b020c 	.word	0x000b020c
 8062240:	460cb430 	.word	0x460cb430
 8062244:	3a10460d 	.word	0x3a10460d
 8062248:	e920bf28 	.word	0xe920bf28
 806224c:	d8fa003a 	.word	0xd8fa003a
 8062250:	bf280752 	.word	0xbf280752
 8062254:	000ae920 	.word	0x000ae920
 8062258:	f840bf48 	.word	0xf840bf48
 806225c:	46601d04 	.word	0x46601d04
 8062260:	4770bc30 	.word	0x4770bc30
 8062264:	f3af 8000 	nop.w
 8062268:	f3af 8000 	nop.w
 806226c:	f3af 8000 	nop.w

08062270 <full_loop4>:
 8062270:	b14a      	cbz	r2, 8062286 <full_loop4+0x16>
 8062272:	2a03      	cmp	r2, #3
 8062274:	d801      	bhi.n	806227a <full_loop4+0xa>
 8062276:	f7a6 bb1b 	b.w	80088b0 <*ABS*0x80088b0>
 806227a:	2a0f      	cmp	r2, #15
 806227c:	d801      	bhi.n	8062282 <full_loop4+0x12>
 806227e:	f7a6 bb1f 	b.w	80088c0 <*ABS*0x80088c0>
 8062282:	f000 b807 	b.w	8062294 <bulk_loop4>
 8062286:	4770      	bx	lr
 8062288:	f3af 8000 	nop.w
 806228c:	f3af 8000 	nop.w
 8062290:	00000000 	.word	0x00000000

08062294 <bulk_loop4>:
 8062294:	210ff361 	.word	0x210ff361
 8062298:	411ff361 	.word	0x411ff361
 806229c:	60014684 	.word	0x60014684
 80622a0:	f8401880 	.word	0xf8401880
 80622a4:	f0201c04 	.word	0xf0201c04
 80622a8:	eba00003 	.word	0xeba00003
 80622ac:	000b020c 	.word	0x000b020c
 80622b0:	460cb430 	.word	0x460cb430
 80622b4:	3a10460d 	.word	0x3a10460d
 80622b8:	e920d303 	.word	0xe920d303
 80622bc:	3a10003a 	.word	0x3a10003a
 80622c0:	0752d2fb 	.word	0x0752d2fb
 80622c4:	e920bf28 	.word	0xe920bf28
 80622c8:	bf48000a 	.word	0xbf48000a
 80622cc:	1d04f840 	.word	0x1d04f840
 80622d0:	bc304660 	.word	0xbc304660
 80622d4:	4770      	.short	0x4770
 80622d6:	bf00      	nop
