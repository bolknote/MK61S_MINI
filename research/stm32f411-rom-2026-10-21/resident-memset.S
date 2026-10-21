/* Annotated address ranges; labels are analytical, not vendor symbols. */

/* fill_small, 1..3 bytes: 16 bytes, [080088B0, 080088C0) */
080088b0: 0244       add      r2, r0
080088b2: 0346       mov      r3, r0
080088b4: 9342       cmp      r3, r2
080088b6: 00d1       bne      #0x80088ba
080088b8: 7047       bx       lr
080088ba: 03f8011b   strb     r1, [r3], #1
080088be: f9e7       b        #0x80088b4

/* fill_short_words, 4..15 bytes: 52 bytes, [080088C0, 080088F4) */
080088c0: c9b2       uxtb     r1, r1
080088c2: 4ff00133   mov.w    r3, #0x1010101
080088c6: 4b43       muls     r3, r1, r3
080088c8: 072a       cmp      r2, #7
080088ca: 30b5       push     {r4, r5, lr}
080088cc: 0360       str      r3, [r0]
080088ce: 03d9       bls      #0x80088d8
080088d0: 0b2a       cmp      r2, #0xb
080088d2: 4360       str      r3, [r0, #4]
080088d4: 88bf       it       hi
080088d6: 8360       strhi    r3, [r0, #8]
080088d8: 12f00305   ands     r5, r2, #3
080088dc: 09d0       beq      #0x80088f2
080088de: 22f00304   bic      r4, r2, #3
080088e2: 0319       adds     r3, r0, r4
080088e4: 9207       lsls     r2, r2, #0x1e
080088e6: 0155       strb     r1, [r0, r4]
080088e8: 48bf       it       mi
080088ea: 5970       strbmi   r1, [r3, #1]
080088ec: 032d       cmp      r5, #3
080088ee: 08bf       it       eq
080088f0: 9970       strbeq   r1, [r3, #2]
080088f2: 30bd       pop      {r4, r5, pc}

/* fill_bulk, >=16 bytes: 88 bytes, [08008934, 0800898C) */
08008934: f0b5       push     {r4, r5, r6, r7, lr}
08008936: 4ff00133   mov.w    r3, #0x1010101
0800893a: ccb2       uxtb     r4, r1
0800893c: 5c43       muls     r4, r3, r4
0800893e: 1618       adds     r6, r2, r0
08008940: 1346       mov      r3, r2
08008942: 0f2b       cmp      r3, #0xf
08008944: a6eb0305   sub.w    r5, r6, r3
08008948: 14d8       bhi      #0x8008974
0800894a: 22f00f05   bic      r5, r2, #0xf
0800894e: 02f00f03   and      r3, r2, #0xf
08008952: 0544       add      r5, r0
08008954: 1e46       mov      r6, r3
08008956: 03eb050c   add.w    ip, r3, r5
0800895a: 032e       cmp      r6, #3
0800895c: aceb0607   sub.w    r7, ip, r6
08008960: 0ed8       bhi      #0x8008980
08008962: 03f00c03   and      r3, r3, #0xc
08008966: 2b44       add      r3, r5
08008968: 02f00302   and      r2, r2, #3
0800896c: 1a44       add      r2, r3
0800896e: 9342       cmp      r3, r2
08008970: 09d1       bne      #0x8008986
08008972: f0bd       pop      {r4, r5, r6, r7, pc}
08008974: 2c60       str      r4, [r5]
08008976: 6c60       str      r4, [r5, #4]
08008978: ac60       str      r4, [r5, #8]
0800897a: ec60       str      r4, [r5, #0xc]
0800897c: 103b       subs     r3, #0x10
0800897e: e0e7       b        #0x8008942
08008980: 3c60       str      r4, [r7]
08008982: 043e       subs     r6, #4
08008984: e9e7       b        #0x800895a
08008986: 03f8011b   strb     r1, [r3], #1
0800898a: f0e7       b        #0x800896e

/* public memset: 24 bytes, [08008A20, 08008A38) */
08008a20: 4ab1       cbz      r2, #0x8008a36
08008a22: 032a       cmp      r2, #3
08008a24: 01d8       bhi      #0x8008a2a
08008a26: fff743bf   b.w      #0x80088b0
08008a2a: 0f2a       cmp      r2, #0xf
08008a2c: 01d8       bhi      #0x8008a32
08008a2e: fff747bf   b.w      #0x80088c0
08008a32: fff77fbf   b.w      #0x8008934
08008a36: 7047       bx       lr
