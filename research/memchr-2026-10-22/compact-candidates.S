/* M4 compact control: paired loads, zero-byte GE flags, and an independent
 * aligned-block counter whose NZ flags survive UADD8/SEL/CBNZ. The short
 * prefix checks the first byte and exhausts n==1 before long dispatch. */
.syntax unified
.thumb
.cpu cortex-m4
.section .text.compact8,"ax",%progbits
.balign 4
.global compact8
.type compact8,%function
.thumb_func
compact8:
 cmp r2,#0
 beq .Lzero
 uxtb r1,r1
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn
 subs r2,#1
 beq .Lzero
 cmp r2,#15
 bhs .Llarge
 adds r0,#1
.Lsmall:
 ldrb r3,[r0],#1
 subs r2,#1
 eor r3,r3,r1
 cbz r3,.LbyteHit
 bne .Lsmall
.Lzero:
 movs r0,#0
.Lreturn:
 bx lr
.LbyteHit:
 subs r0,#1
 bx lr
.Llarge:
 adds r2,#1
 tst r0,#7
 beq .Laligned
 adds r0,#1
 subs r2,#1
.Lprefix:
 tst r0,#7
 beq .Laligned
 ldrb r3,[r0]
 cmp r3,r1
 beq .Lreturn
 adds r0,#1
 subs r2,#1
 b .Lprefix
.Laligned:
 push {r4,r5,r6,r7}
 bic r4,r2,#7
 and r2,r2,#7
 orr r1,r1,r1,lsl#8
 orr r1,r1,r1,lsl#16
 mvn r7,#0
 movs r3,#0
.Lpair:
 ldmia r0!,{r5,r6}
 subs r4,#8
 eor r5,r5,r1
 eor r6,r6,r1
 uadd8 r5,r5,r7
 sel r5,r3,r7
 uadd8 r6,r6,r7
 sel r6,r5,r7
 cbnz r6,.LpairHit
 bne .Lpair
 pop {r4,r5,r6,r7}
 uxtb r1,r1
 cmp r2,#0
 bne .Lsmall
 b .Lzero
.LpairHit:
 cmp r5,#0
 bne .Lfirst
 mov r5,r6
 subs r0,#4
 b .Lfound
.Lfirst:
 subs r0,#8
.Lfound:
 rbit r5,r5
 clz r5,r5
 add r0,r0,r5,lsr#3
 pop {r4,r5,r6,r7}
 bx lr
.size compact8,.-compact8
