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
 lsrs r0,r1,#9
 subs r0,#128
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
 asrs r2,#15
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
 .hword 65280,64776,64280,63791,63310,62836,62368,61908
 .hword 61455,61008,60567,60133,59705,59283,58867,58457
 .hword 58052,57653,57260,56871,56488,56111,55738,55370
 .hword 55007,54648,54295,53946,53601,53261,52924,52593
 .hword 52265,51941,51622,51306,50994,50686,50382,50081
 .hword 49784,49490,49200,48913,48629,48349,48072,47798
 .hword 47527,47259,46995,46733,46474,46218,45964,45714
 .hword 45466,45221,44979,44739,44501,44267,44034,43804
 .hword 43577,43351,43129,42908,42690,42473,42259,42048
 .hword 41838,41630,41425,41221,41020,40820,40622,40427
 .hword 40233,40041,39850,39662,39475,39290,39107,38926
 .hword 38746,38568,38391,38216,38043,37871,37701,37532
 .hword 37365,37200,37035,36873,36711,36551,36393,36235
 .hword 36080,35925,35772,35620,35469,35320,35172,35025
 .hword 34879,34735,34592,34450,34309,34169,34030,33893
 .hword 33756,33621,33487,33354,33222,33091,32961,32832
#endif
.section .note.GNU-stack,"",%progbits
