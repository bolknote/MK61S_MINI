200002f4: 61f30f21   bfi      r1, r1, #8, #8
200002f8: 61f31f41   bfi      r1, r1, #0x10, #0x10
200002fc: 8446       mov      ip, r0
200002fe: 0160       str      r1, [r0]
20000300: 8018       adds     r0, r0, r2
20000302: 40f8041c   str      r1, [r0, #-0x4]
20000306: 20f00300   bic      r0, r0, #3
2000030a: a0eb0c02   sub.w    r2, r0, ip
2000030e: 0b00       movs     r3, r1
20000310: 30b4       push     {r4, r5}
20000312: 0c46       mov      r4, r1
20000314: 0d46       mov      r5, r1
20000316: 103a       subs     r2, #0x10
20000318: 28bf       it       hs
2000031a: 20e93a00   stmdbhs  r0!, {r1, r3, r4, r5}
2000031e: fad8       bhi      #0x20000316
20000320: 5207       lsls     r2, r2, #0x1d
20000322: 28bf       it       hs
20000324: 20e90a00   stmdbhs  r0!, {r1, r3}
20000328: 48bf       it       mi
2000032a: 40f8041d   strmi    r1, [r0, #-0x4]!
2000032e: 6046       mov      r0, ip
20000330: 30bc       pop      {r4, r5}
20000332: 7047       bx       lr
