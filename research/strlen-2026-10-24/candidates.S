/* strlen candidates for ordinary little-endian SRAM/Flash.
 * byte* never read past NUL. word* read only aligned words containing NUL;
 * dsp8/dsp32 use aligned eight-byte groups, like this toolchain's M4 newlib.
 * Every group is checked before the next group is read.
 */
.syntax unified
.thumb
.text

.p2align 4
.global byte1
.type byte1,%function
.thumb_func
byte1:
  mov r1,r0
1:
#if defined(__ARM_ARCH_6M__)
  ldrb r2,[r0]
  adds r0,#1
#else
  ldrb r2,[r0],#1
#endif
  cmp r2,#0
  bne 1b
  subs r0,r0,r1
  subs r0,#1
  bx lr
.size byte1,.-byte1

.p2align 4
.global byte4
.type byte4,%function
.thumb_func
byte4:
  mov r1,r0
1:
  ldrb r2,[r0,#0]
  cmp r2,#0
  beq 5f
  ldrb r2,[r0,#1]
  cmp r2,#0
  beq 4f
  ldrb r2,[r0,#2]
  cmp r2,#0
  beq 3f
  ldrb r2,[r0,#3]
  cmp r2,#0
  beq 2f
  adds r0,#4
  b 1b
2: adds r0,#1
3: adds r0,#1
4: adds r0,#1
5:
  subs r0,r0,r1
  bx lr
.size byte4,.-byte4

.macro WORD name, count, dsp
.p2align 4
.global \name
.type \name,%function
.thumb_func
\name:
  mov r1,r0
.Lalign\@:
  ldrb r2,[r0]
  cmp r2,#0
  beq .Lplain_return\@
  lsls r3,r0,#30
  beq .Lbulk\@
  adds r0,#1
  b .Lalign\@
.Lbulk\@:
  push {r4,r5}
  ldr r4,.Lones\@
.if !\dsp
  lsls r5,r4,#7
.endif
.Lloop\@:
.rept \count
#if defined(__ARM_ARCH_6M__)
  ldmia r0!,{r2}
#else
  ldr r2,[r0],#4
#endif
.if \dsp
  uqsub8 r3,r4,r2
  cmp r3,#0
.else
  subs r3,r2,r4
  bics r3,r2
  tst r3,r5
.endif
  bne .Lfound\@
.endr
  b .Lloop\@
.Lfound\@:
  subs r0,#4
.if \dsp
  rbit r3,r3
  clz r3,r3
  lsrs r3,#3
  adds r0,r0,r3
.else
.Ltail\@:
  uxtb r3,r2
  cmp r3,#0
  beq .Lfinish\@
  lsrs r2,#8
  adds r0,#1
  b .Ltail\@
.Lfinish\@:
.endif
  subs r0,r0,r1
  pop {r4,r5}
  bx lr
.Lplain_return\@:
  subs r0,r0,r1
  bx lr
.p2align 2
.Lones\@:
  .word 0x01010101
.size \name,.-\name
.endm

WORD word1,1,0
WORD word2,2,0
WORD word4,4,0

#if defined(__ARM_ARCH_7EM__)
WORD dsp1,1,1
WORD dsp4,4,1

.macro DOUBLE name, count
.p2align 4
.global \name
.type \name,%function
.thumb_func
\name:
  mov r1,r0
.Lalign\@:
  ldrb r2,[r0]
  cmp r2,#0
  beq .Lplain_return\@
  lsls r3,r0,#29
  beq .Lbulk\@
  adds r0,#1
  b .Lalign\@
.Lbulk\@:
  push {r4,r5}
  ldr r4,.Lones\@
.Lloop\@:
.rept \count
  ldrd r2,r3,[r0],#8
  uqsub8 r5,r4,r2
  uqsub8 r12,r4,r3
  orrs r12,r12,r5
  bne .Lfound\@
.endr
  b .Lloop\@
.Lfound\@:
  subs r0,#8
  cmp r5,#0
  bne .Lfirst\@
  adds r0,#4
  mov r5,r12
.Lfirst\@:
  rbit r5,r5
  clz r5,r5
  lsrs r5,#3
  adds r0,r0,r5
  subs r0,r0,r1
  pop {r4,r5}
  bx lr
.Lplain_return\@:
  subs r0,r0,r1
  bx lr
.p2align 2
.Lones\@:
  .word 0x01010101
.size \name,.-\name
.endm

DOUBLE dsp8,1
DOUBLE dsp32,4
#endif
.section .note.GNU-stack,"",%progbits
