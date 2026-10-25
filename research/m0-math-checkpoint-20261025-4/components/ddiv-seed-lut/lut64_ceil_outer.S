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
 lsrs r0,r1,#10
 subs r0,#64
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
 .hword 65027,64035,63072,62137,61230,60349,59493,58661
 .hword 57852,57065,56299,55553,54827,54120,53430,52758
 .hword 52103,51463,50840,50231,49636,49056,48489,47934
 .hword 47393,46863,46345,45839,45343,44858,44384,43919
 .hword 43464,43018,42581,42153,41734,41323,40920,40524
 .hword 40136,39756,39383,39016,38657,38304,37957,37617
 .hword 37282,36954,36631,36314,36002,35696,35394,35098
 .hword 34807,34521,34239,33961,33689,33420,33156,32896
#endif
.section .note.GNU-stack,"",%progbits
