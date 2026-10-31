.syntax unified
.cpu cortex-m0plus
.thumb
.section .text.experiment_udiv32,"ax",%progbits
.global experiment_udiv32
.type experiment_udiv32,%function
.thumb_func
experiment_udiv32:
 cmp r1,#0
 beq .Lsoftware
 ldr r2,=0xd0000078
 ldr r3,[r2]
 lsrs r3,#2
 bcs .Lsoftware
 subs r2,#24
 str r0,[r2]
 str r1,[r2,#4]
 b 1f
1: b 1f
1: b 1f
1: b 1f
1: ldr r0,[r2,#16]
 bx lr
.Lsoftware:
 // CPU-only restoring division for a busy SIO. Do not touch its state.
 cmp r1,#0
 bne 1f
 movs r0,#0
 mvns r0,r0
 bx lr
1: push {r4-r5,lr}
 movs r2,#0
 movs r3,#0
 movs r4,#32
2: lsls r0,#1
 adcs r3,r3
 bcs 4f
 lsls r2,#1
 cmp r3,r1
 blo 3f
 b 5f
4: lsls r2,#1
5:
 subs r3,r1
 adds r2,#1
3: subs r4,#1
 bne 2b
 mov r0,r2
 pop {r4-r5,pc}
.ltorg
.size experiment_udiv32,.-experiment_udiv32
