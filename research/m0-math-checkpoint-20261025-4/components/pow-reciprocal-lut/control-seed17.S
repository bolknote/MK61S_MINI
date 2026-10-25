#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
// Exact floor((2^32-1)/D), 2^16 <= D < 2^17, D in R1.
// The first quotient bit is always1; process the remaining15 one bits.
// Private software-ddiv continuation also requires R12 unchanged.
.section .m0_ddiv_seed17,"ax",%progbits
.p2align 1
.global mk61_m0_ddiv_seed17
.hidden mk61_m0_ddiv_seed17
.type mk61_m0_ddiv_seed17,%function
.thumb_func
mk61_m0_ddiv_seed17:
 movs r0,#1
 lsls r0,#17
 subs r0,#1
 subs r0,r1
 movs r2,#1
.rept 15
 lsls r0,#1
 adds r0,#1
 cmp r0,r1
 bcc 1f
 subs r0,r1
1:
 adcs r2,r2
.endr
 mov r0,r2
 bx lr
.size mk61_m0_ddiv_seed17,.-mk61_m0_ddiv_seed17
#endif
