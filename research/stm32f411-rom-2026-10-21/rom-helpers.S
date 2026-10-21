/* Annotated address ranges; labels are analytical, not vendor symbols. */

/* copy words; NOT ISO C memcpy: 34 bytes, [1FFF0A4C, 1FFF0A6E) */
1fff0a4c: 30b5       push     {r4, r5, lr}
1fff0a4e: 12f0030f   tst.w    r2, #3
1fff0a52: 1cbf       itt      ne
1fff0a54: 02f0fc02   andne    r2, r2, #0xfc
1fff0a58: 121d       addne    r2, r2, #4
1fff0a5a: 1300       movs     r3, r2
1fff0a5c: 05e0       b        #0x1fff0a6a
1fff0a5e: 5c42       rsbs     r4, r3, #0
1fff0a60: 5518       adds     r5, r2, r1
1fff0a62: 6459       ldr      r4, [r4, r5]
1fff0a64: c51a       subs     r5, r0, r3
1fff0a66: 1b1f       subs     r3, r3, #4
1fff0a68: 5451       str      r4, [r2, r5]
1fff0a6a: f8d1       bne      #0x1fff0a5e
1fff0a6c: 30bd       pop      {r4, r5, pc}

/* high nibbles to uppercase UTF-16LE hex; no terminator: 40 bytes, [1FFF27C0, 1FFF27E8) */
1fff27c0: 30b5       push     {r4, r5, lr}
1fff27c2: 0023       movs     r3, #0
1fff27c4: 0025       movs     r5, #0
1fff27c6: 06e0       b        #0x1fff27d6
1fff27c8: 01f81340   strb.w   r4, [r1, r3, lsl #1]
1fff27cc: 01eb4304   add.w    r4, r1, r3, lsl #1
1fff27d0: 0001       lsls     r0, r0, #4
1fff27d2: 6570       strb     r5, [r4, #1]
1fff27d4: 5b1c       adds     r3, r3, #1
1fff27d6: 9342       cmp      r3, r2
1fff27d8: 05da       bge      #0x1fff27e6
1fff27da: 040f       lsrs     r4, r0, #0x1c
1fff27dc: 0a2c       cmp      r4, #0xa
1fff27de: 34bf       ite      lo
1fff27e0: 3034       addlo    r4, #0x30
1fff27e2: 3734       addhs    r4, #0x37
1fff27e4: f0e7       b        #0x1fff27c8
1fff27e6: 30bd       pop      {r4, r5, pc}

/* swap low two bytes; u16 input: 10 bytes, [1FFF3A60, 1FFF3A6A) */
1fff3a60: 0106       lsls     r1, r0, #0x18
1fff3a62: 090c       lsrs     r1, r1, #0x10
1fff3a64: 41ea1020   orr.w    r0, r1, r0, lsr #8
1fff3a68: 7047       bx       lr

/* fill: r0=dest, r1=size, r2=value; ISO C adapter required: 102 bytes, [1FFF3BD4, 1FFF3C3A) */
1fff3bd4: 62f30f22   bfi      r2, r2, #8, #8
1fff3bd8: 62f31f42   bfi      r2, r2, #0x10, #0x10
1fff3bdc: 4018       adds     r0, r0, r1
1fff3bde: 10f00303   ands     r3, r0, #3
1fff3be2: 08d0       beq      #0x1fff3bf6
1fff3be4: c91a       subs     r1, r1, r3
1fff3be6: 1fd3       blo      #0x1fff3c28
1fff3be8: db07       lsls     r3, r3, #0x1f
1fff3bea: 48bf       it       mi
1fff3bec: 00f8012d   strbmi   r2, [r0, #-0x1]!
1fff3bf0: 28bf       it       hs
1fff3bf2: 20f8022d   strhhs   r2, [r0, #-0x2]!
1fff3bf6: 1300       movs     r3, r2
1fff3bf8: 30b4       push     {r4, r5}
1fff3bfa: 1446       mov      r4, r2
1fff3bfc: 1546       mov      r5, r2
1fff3bfe: 1039       subs     r1, #0x10
1fff3c00: 28bf       it       hs
1fff3c02: 20e93c00   stmdbhs  r0!, {r2, r3, r4, r5}
1fff3c06: fad8       bhi      #0x1fff3bfe
1fff3c08: 4907       lsls     r1, r1, #0x1d
1fff3c0a: 28bf       it       hs
1fff3c0c: 20e90c00   stmdbhs  r0!, {r2, r3}
1fff3c10: 48bf       it       mi
1fff3c12: 40f8042d   strmi    r2, [r0, #-0x4]!
1fff3c16: 8900       lsls     r1, r1, #2
1fff3c18: 28bf       it       hs
1fff3c1a: 20f8022d   strhhs   r2, [r0, #-0x2]!
1fff3c1e: 48bf       it       mi
1fff3c20: 00f8012d   strbmi   r2, [r0, #-0x1]!
1fff3c24: 30bc       pop      {r4, r5}
1fff3c26: 7047       bx       lr
1fff3c28: c918       adds     r1, r1, r3
1fff3c2a: 18bf       it       ne
1fff3c2c: 00f8012d   strbne   r2, [r0, #-0x1]!
1fff3c30: cb07       lsls     r3, r1, #0x1f
1fff3c32: 28bf       it       hs
1fff3c34: 00f8012d   strbhs   r2, [r0, #-0x1]!
1fff3c38: 7047       bx       lr
