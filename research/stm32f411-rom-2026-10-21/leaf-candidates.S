
{"entry": "1FFF06D8", "instructions": 6, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff06d8: ldr      r0, [r4]
1fff06da: ldr      r1, [r4, #4]
1fff06dc: uxtb     r0, r0
1fff06de: uxtb     r1, r1
1fff06e0: cmp      r0, r1
1fff06e2: bx       lr

{"entry": "1FFF0782", "instructions": 6, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff0782: ldr      r1, [r4]
1fff0784: eors     r1, r0
1fff0786: str      r1, [r4]
1fff0788: strb     r0, [r8], #1
1fff078c: subs     r5, r5, #1
1fff078e: bx       lr

{"entry": "1FFF08FA", "instructions": 7, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff08fa: mov      r5, r0
1fff08fc: ldr      r0, [r4]
1fff08fe: eors     r0, r5
1fff0900: str      r0, [r4]
1fff0902: strb     r5, [r8], #1
1fff0906: subs     r7, r7, #1
1fff0908: bx       lr

{"entry": "1FFF0A36", "instructions": 4, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff0a36: mov      r2, r6
1fff0a38: mov      r1, r5
1fff0a3a: mov      r0, r4
1fff0a3c: bx       lr

{"entry": "1FFF0A4C", "instructions": 15, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff0a4c: push     {r4, r5, lr}
1fff0a4e: tst.w    r2, #3
1fff0a52: itt      ne
1fff0a54: and      r2, r2, #0xfc
1fff0a58: adds     r2, r2, #4
1fff0a5a: movs     r3, r2
1fff0a5c: b        #0x1fff0a6a
1fff0a5e: rsbs     r4, r3, #0
1fff0a60: adds     r5, r2, r1
1fff0a62: ldr      r4, [r4, r5]
1fff0a64: subs     r5, r0, r3
1fff0a66: subs     r3, r3, #4
1fff0a68: str      r4, [r2, r5]
1fff0a6a: bne      #0x1fff0a5e
1fff0a6c: pop      {r4, r5, pc}

{"entry": "1FFF1018", "instructions": 2, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1018: msr      msp, r0
1fff101c: bx       lr

{"entry": "1FFF1020", "instructions": 2, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1020: cpsid    i
1fff1022: bx       lr

{"entry": "1FFF1028", "instructions": 2, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1028: cpsie    i
1fff102a: bx       lr

{"entry": "1FFF102E", "instructions": 13, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff102e: ldr      r1, [r0], #4
1fff1032: cbz      r1, #0x1fff104e
1fff1034: ldr      r2, [r0], #4
1fff1038: lsls     r3, r2, #0x1f
1fff103a: itt      mi
1fff103c: sub.w    r3, sb, #1
1fff1040: adds     r2, r3, r2
1fff1042: movs     r3, #0
1fff1044: str      r3, [r2], #4
1fff1048: subs     r1, r1, #4
1fff104a: bne      #0x1fff1042
1fff104c: b        #0x1fff102e
1fff104e: bx       lr

{"entry": "1FFF17A4", "instructions": 4, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff17a4: ldr.w    r0, [sl, #8]
1fff17a8: rsb.w    r0, r0, #0x80000
1fff17ac: str      r0, [r4, #0x20]
1fff17ae: bx       lr

{"entry": "1FFF17BA", "instructions": 10, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff17ba: movs     r1, #0x64
1fff17bc: udiv     r1, r0, r1
1fff17c0: ldr      r0, [sp]
1fff17c2: adds     r0, r1, r0
1fff17c4: movw     r1, #0x1ce8
1fff17c8: udiv     r0, r0, r1
1fff17cc: lsrs     r0, r0, #1
1fff17ce: movs     r1, #0xa
1fff17d0: muls     r0, r1, r0
1fff17d2: bx       lr

{"entry": "1FFF1BD8", "instructions": 4, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1bd8: strb.w   r0, [sp, #4]
1fff1bdc: ldrb.w   r0, [sp, #4]
1fff1be0: cmp      r0, #1
1fff1be2: bx       lr

{"entry": "1FFF1CEC", "instructions": 4, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1cec: str      r0, [sp]
1fff1cee: ldr      r0, [sp]
1fff1cf0: cmp      r0, #0
1fff1cf2: bx       lr

{"entry": "1FFF1D82", "instructions": 6, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff1d82: ldr      r0, [sp]
1fff1d84: ldrh.w   r1, [sp, #0x10]
1fff1d88: uxtb     r1, r1
1fff1d8a: eors     r0, r1
1fff1d8c: str      r0, [sp]
1fff1d8e: bx       lr

{"entry": "1FFF20F6", "instructions": 7, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff20f6: str      r0, [r4, #8]
1fff20f8: ldr      r0, [r4, #4]
1fff20fa: ldr      r1, [r4, #8]
1fff20fc: uxtb     r0, r0
1fff20fe: uxtb     r1, r1
1fff2100: cmp      r0, r1
1fff2102: bx       lr

{"entry": "1FFF2276", "instructions": 1, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff2276: bx       lr

{"entry": "1FFF24E4", "instructions": 8, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff24e4: cmp      r1, #4
1fff24e6: it       lo
1fff24e8: cmp      r0, #3
1fff24ea: blo      #0x1fff24f0
1fff24ec: movs     r0, #2
1fff24ee: bx       lr
1fff24f0: movs     r0, #0
1fff24f2: bx       lr

{"entry": "1FFF27C0", "instructions": 18, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff27c0: push     {r4, r5, lr}
1fff27c2: movs     r3, #0
1fff27c4: movs     r5, #0
1fff27c6: b        #0x1fff27d6
1fff27c8: strb.w   r4, [r1, r3, lsl #1]
1fff27cc: add.w    r4, r1, r3, lsl #1
1fff27d0: lsls     r0, r0, #4
1fff27d2: strb     r5, [r4, #1]
1fff27d4: adds     r3, r3, #1
1fff27d6: cmp      r3, r2
1fff27d8: bge      #0x1fff27e6
1fff27da: lsrs     r4, r0, #0x1c
1fff27dc: cmp      r4, #0xa
1fff27de: ite      lo
1fff27e0: adds     r4, #0x30
1fff27e2: adds     r4, #0x37
1fff27e4: b        #0x1fff27c8
1fff27e6: pop      {r4, r5, pc}

{"entry": "1FFF2908", "instructions": 9, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff2908: and      r0, r1, #1
1fff290c: addw     r1, pc, #0x10
1fff2910: ldrh.w   r0, [r1, r0, lsl #1]
1fff2914: strb     r0, [r2, #1]
1fff2916: lsrs     r0, r0, #8
1fff2918: strb     r0, [r2, #2]
1fff291a: movs     r0, #0
1fff291c: strb     r0, [r2, #3]
1fff291e: bx       lr

{"entry": "1FFF2924", "instructions": 2, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff2924: movs     r0, #0
1fff2926: bx       lr

{"entry": "1FFF2928", "instructions": 1, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff2928: bx       lr

{"entry": "1FFF30F0", "instructions": 1, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff30f0: bx       lr

{"entry": "1FFF3226", "instructions": 1, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3226: bx       lr

{"entry": "1FFF325A", "instructions": 43, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff325a: subs     r1, r0, r5
1fff325c: movs     r2, #0xff
1fff325e: adds     r0, r5, r6
1fff3260: b.w      #0x1fff3bd4
1fff3bd4: bfi      r2, r2, #8, #8
1fff3bd8: bfi      r2, r2, #0x10, #0x10
1fff3bdc: adds     r0, r0, r1
1fff3bde: ands     r3, r0, #3
1fff3be2: beq      #0x1fff3bf6
1fff3be4: subs     r1, r1, r3
1fff3be6: blo      #0x1fff3c28
1fff3be8: lsls     r3, r3, #0x1f
1fff3bea: it       mi
1fff3bec: strb     r2, [r0, #-0x1]!
1fff3bf0: it       hs
1fff3bf2: strh     r2, [r0, #-0x2]!
1fff3bf6: movs     r3, r2
1fff3bf8: push     {r4, r5}
1fff3bfa: mov      r4, r2
1fff3bfc: mov      r5, r2
1fff3bfe: subs     r1, #0x10
1fff3c00: it       hs
1fff3c02: stmdb    r0!, {r2, r3, r4, r5}
1fff3c06: bhi      #0x1fff3bfe
1fff3c08: lsls     r1, r1, #0x1d
1fff3c0a: it       hs
1fff3c0c: stmdb    r0!, {r2, r3}
1fff3c10: it       mi
1fff3c12: str      r2, [r0, #-0x4]!
1fff3c16: lsls     r1, r1, #2
1fff3c18: it       hs
1fff3c1a: strh     r2, [r0, #-0x2]!
1fff3c1e: it       mi
1fff3c20: strb     r2, [r0, #-0x1]!
1fff3c24: pop      {r4, r5}
1fff3c26: bx       lr
1fff3c28: adds     r1, r1, r3
1fff3c2a: it       ne
1fff3c2c: strb     r2, [r0, #-0x1]!
1fff3c30: lsls     r3, r1, #0x1f
1fff3c32: it       hs
1fff3c34: strb     r2, [r0, #-0x1]!
1fff3c38: bx       lr

{"entry": "1FFF350A", "instructions": 5, "calls": [], "literal_values": {"1FFF39A4": "00030D41"}, "indirect_sites": []}
1fff350a: ldr      r0, [r0]
1fff350c: ldr      r1, [sp]
1fff350e: str      r1, [r0, #0x10]
1fff3510: ldr.w    r1, [pc, #0x490]
1fff3514: bx       lr

{"entry": "1FFF3A5C", "instructions": 1, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3a5c: bx       lr

{"entry": "1FFF3A60", "instructions": 4, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3a60: lsls     r1, r0, #0x18
1fff3a62: lsrs     r1, r1, #0x10
1fff3a64: orr.w    r0, r1, r0, lsr #8
1fff3a68: bx       lr

{"entry": "1FFF3ACC", "instructions": 7, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3acc: str      r4, [r3, #8]
1fff3ace: str      r1, [r3, #0x10]
1fff3ad0: str      r4, [r3, #0x14]
1fff3ad2: adds     r2, r2, #1
1fff3ad4: str      r4, [r3, #0x18]
1fff3ad6: cmp      r2, #4
1fff3ad8: bx       lr

{"entry": "1FFF3BD4", "instructions": 39, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3bd4: bfi      r2, r2, #8, #8
1fff3bd8: bfi      r2, r2, #0x10, #0x10
1fff3bdc: adds     r0, r0, r1
1fff3bde: ands     r3, r0, #3
1fff3be2: beq      #0x1fff3bf6
1fff3be4: subs     r1, r1, r3
1fff3be6: blo      #0x1fff3c28
1fff3be8: lsls     r3, r3, #0x1f
1fff3bea: it       mi
1fff3bec: strb     r2, [r0, #-0x1]!
1fff3bf0: it       hs
1fff3bf2: strh     r2, [r0, #-0x2]!
1fff3bf6: movs     r3, r2
1fff3bf8: push     {r4, r5}
1fff3bfa: mov      r4, r2
1fff3bfc: mov      r5, r2
1fff3bfe: subs     r1, #0x10
1fff3c00: it       hs
1fff3c02: stmdb    r0!, {r2, r3, r4, r5}
1fff3c06: bhi      #0x1fff3bfe
1fff3c08: lsls     r1, r1, #0x1d
1fff3c0a: it       hs
1fff3c0c: stmdb    r0!, {r2, r3}
1fff3c10: it       mi
1fff3c12: str      r2, [r0, #-0x4]!
1fff3c16: lsls     r1, r1, #2
1fff3c18: it       hs
1fff3c1a: strh     r2, [r0, #-0x2]!
1fff3c1e: it       mi
1fff3c20: strb     r2, [r0, #-0x1]!
1fff3c24: pop      {r4, r5}
1fff3c26: bx       lr
1fff3c28: adds     r1, r1, r3
1fff3c2a: it       ne
1fff3c2c: strb     r2, [r0, #-0x1]!
1fff3c30: lsls     r3, r1, #0x1f
1fff3c32: it       hs
1fff3c34: strb     r2, [r0, #-0x1]!
1fff3c38: bx       lr

{"entry": "1FFF3BF8", "instructions": 19, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3bf8: push     {r4, r5}
1fff3bfa: mov      r4, r2
1fff3bfc: mov      r5, r2
1fff3bfe: subs     r1, #0x10
1fff3c00: it       hs
1fff3c02: stmdb    r0!, {r2, r3, r4, r5}
1fff3c06: bhi      #0x1fff3bfe
1fff3c08: lsls     r1, r1, #0x1d
1fff3c0a: it       hs
1fff3c0c: stmdb    r0!, {r2, r3}
1fff3c10: it       mi
1fff3c12: str      r2, [r0, #-0x4]!
1fff3c16: lsls     r1, r1, #2
1fff3c18: it       hs
1fff3c1a: strh     r2, [r0, #-0x2]!
1fff3c1e: it       mi
1fff3c20: strb     r2, [r0, #-0x1]!
1fff3c24: pop      {r4, r5}
1fff3c26: bx       lr

{"entry": "1FFF3FB2", "instructions": 20, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3fb2: ldr      r1, [r0, #8]
1fff3fb4: ldr      r2, [r0, #0xc]
1fff3fb6: cmp      r1, r2
1fff3fb8: bne      #0x1fff3fd2
1fff3fba: b        #0x1fff3fcc
1fff3fbc: ldr      r2, [r0]
1fff3fbe: ldr      r1, [r2]
1fff3fc0: adds     r1, r1, r2
1fff3fc2: ldr      r3, [r2, #4]
1fff3fc4: adds     r3, r3, r1
1fff3fc6: str      r3, [r0, #0xc]
1fff3fc8: adds     r2, #8
1fff3fca: str      r2, [r0]
1fff3fcc: ldr      r2, [r0, #0xc]
1fff3fce: cmp      r1, r2
1fff3fd0: beq      #0x1fff3fbc
1fff3fd2: adds     r2, r1, #1
1fff3fd4: str      r2, [r0, #8]
1fff3fd6: ldrb     r0, [r1]
1fff3fd8: bx       lr

{"entry": "1FFF4118", "instructions": 22, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff3fb2: ldr      r1, [r0, #8]
1fff3fb4: ldr      r2, [r0, #0xc]
1fff3fb6: cmp      r1, r2
1fff3fb8: bne      #0x1fff3fd2
1fff3fba: b        #0x1fff3fcc
1fff3fbc: ldr      r2, [r0]
1fff3fbe: ldr      r1, [r2]
1fff3fc0: adds     r1, r1, r2
1fff3fc2: ldr      r3, [r2, #4]
1fff3fc4: adds     r3, r3, r1
1fff3fc6: str      r3, [r0, #0xc]
1fff3fc8: adds     r2, #8
1fff3fca: str      r2, [r0]
1fff3fcc: ldr      r2, [r0, #0xc]
1fff3fce: cmp      r1, r2
1fff3fd0: beq      #0x1fff3fbc
1fff3fd2: adds     r2, r1, #1
1fff3fd4: str      r2, [r0, #8]
1fff3fd6: ldrb     r0, [r1]
1fff3fd8: bx       lr
1fff4118: add      r0, sp, #0xc
1fff411a: b        #0x1fff3fb2

{"entry": "1FFF411C", "instructions": 8, "calls": [], "literal_values": {"1FFF4134": "00020026"}, "indirect_sites": []}
1fff411c: movs     r0, #1
1fff411e: b.w      #0x1fff4124
1fff4124: mov      r8, r8
1fff4126: mov      r8, r8
1fff4128: ldr      r2, [pc, #8]
1fff412a: movs     r1, r2
1fff412c: movs     r0, #0x18
1fff412e: bkpt     #0xab

{"entry": "1FFF4124", "instructions": 6, "calls": [], "literal_values": {"1FFF4134": "00020026"}, "indirect_sites": []}
1fff4124: mov      r8, r8
1fff4126: mov      r8, r8
1fff4128: ldr      r2, [pc, #8]
1fff412a: movs     r1, r2
1fff412c: movs     r0, #0x18
1fff412e: bkpt     #0xab

{"entry": "1FFF423E", "instructions": 2, "calls": [], "literal_values": {}, "indirect_sites": []}
1fff423e: movs     r0, #1
1fff4240: bx       lr
