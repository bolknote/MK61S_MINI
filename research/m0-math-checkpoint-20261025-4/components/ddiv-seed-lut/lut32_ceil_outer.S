#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
// Own exact floor((2^32-1)/D), 65536<=D<=131071, R1=D.
// R12 and all callee-saved registers preserved; R0,R2,R3,NZCV clobbered.
.section .m0_ddiv_seed17,"ax",%progbits
.p2align 2
.global mk61_m0_ddiv_seed17
.hidden mk61_m0_ddiv_seed17
.type mk61_m0_ddiv_seed17,%function
.thumb_func
mk61_m0_ddiv_seed17:
 lsrs r0,r1,#11
 subs r0,#32
 lsls r0,#1
 adr r2,.Lseed_table
 ldrh r0,[r2,r0]
 // x=ceil(D/2). Signed folded product represents (x*u-2^31)*2.
 adds r2,r1,#1
 lsrs r2,#1
 muls r2,r0
 lsls r2,#1
 asrs r2,#17
 muls r2,r0
 negs r2,r2
 asrs r2,#15
 negs r2,r2
 subs r0,r2
 // Signed exact residual N-q*D; low32 product suffices by the bound.
 movs r3,r0
 muls r3,r1
 mvns r3,r3
 bpl .Lseed_low
.Lseed_high_loop:
 subs r0,#1
 adds r3,r1
 bmi .Lseed_high_loop
 bx lr
.Lseed_low:
 cmp r3,r1
 bcc .Lseed_done
.Lseed_low_loop:
 adds r0,#1
 subs r3,r1
 cmp r3,r1
 bcs .Lseed_low_loop
.Lseed_done:
 bx lr
.size mk61_m0_ddiv_seed17,.-mk61_m0_ddiv_seed17
.p2align 2
.Lseed_table:
 .hword 64527,62601,60787,59074,57456,55924,54471,53092
 .hword 51781,50533,49344,48210,47127,46091,45100,44150
 .hword 43240,42366,41527,40721,39945,39199,38479,37786
 .hword 37117,36472,35848,35246,34663,34100,33554,33026
#endif
.section .note.GNU-stack,"",%progbits
