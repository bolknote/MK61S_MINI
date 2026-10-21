200002f4: 61f30f21   bfi      r1, r1, #8, #8
200002f8: 61f31f41   bfi      r1, r1, #0x10, #0x10
200002fc: 8018       adds     r0, r0, r2
200002fe: 10f00303   ands     r3, r0, #3
20000302: 07d0       beq      #0x20000314
20000304: d21a       subs     r2, r2, r3
20000306: db07       lsls     r3, r3, #0x1f
20000308: 48bf       it       mi
2000030a: 00f8011d   strbmi   r1, [r0, #-0x1]!
2000030e: 28bf       it       hs
20000310: 20f8021d   strhhs   r1, [r0, #-0x2]!
20000314: 0b00       movs     r3, r1
20000316: 30b4       push     {r4, r5}
20000318: 0c46       mov      r4, r1
2000031a: 0d46       mov      r5, r1
2000031c: 103a       subs     r2, #0x10
2000031e: 28bf       it       hs
20000320: 20e93a00   stmdbhs  r0!, {r1, r3, r4, r5}
20000324: fad8       bhi      #0x2000031c
20000326: 5207       lsls     r2, r2, #0x1d
20000328: 28bf       it       hs
2000032a: 20e90a00   stmdbhs  r0!, {r1, r3}
2000032e: 48bf       it       mi
20000330: 40f8041d   strmi    r1, [r0, #-0x4]!
20000334: 9200       lsls     r2, r2, #2
20000336: 28bf       it       hs
20000338: 20f8021d   strhhs   r1, [r0, #-0x2]!
2000033c: 48bf       it       mi
2000033e: 00f8011d   strbmi   r1, [r0, #-0x1]!
20000342: 30bc       pop      {r4, r5}
20000344: 7047       bx       lr
