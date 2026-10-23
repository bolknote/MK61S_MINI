// Exact floor(delta*2^29/den), 0<=delta<=2^41, odd2049<=den<=4095.
// Consume quotient/remainder pairs directly for three radix2^20 digits.
// A pending caller's SIO operation takes the unchanged software path.
.section .m0_pow_extension,"ax",%progbits
.align 2
.global mk61_m0_log_ratio70
.type mk61_m0_log_ratio70,%function
.thumb_func
mk61_m0_log_ratio70:
 ldr r3,=0xd0000078
 ldr r3,[r3]
 lsrs r3,#2
 bcs .Llog_ratio70_slow
 push {r4-r6,lr}
 movs r4,r0
 lsrs r0,#11
 lsls r1,#21
 orrs r0,r1
 ldr r3,=0xd0000060
 str r0,[r3]
 str r2,[r3,#4]
 // Two independent ALU operations and three taken branches: >=8cycles.
 lsls r4,#21
 lsrs r4,#12
 b 1f
1: b 1f
1: b 1f
1:
 ldr r0,[r3,#20]
 ldr r6,[r3,#16]
 lsls r0,#20
 orrs r0,r4
 str r0,[r3]
 str r2,[r3,#4]
 lsls r6,#8
 movs r5,r2
 b 1f
1: b 1f
1: b 1f
1:
 ldr r0,[r3,#20]
 ldr r4,[r3,#16]
 lsls r0,#20
 str r0,[r3]
 str r5,[r3,#4]
 // Four independent ALU operations and two taken branches: >=8cycles.
 movs r1,r4
 lsrs r1,#12
 orrs r1,r6
 lsls r4,#20
 b 1f
1: b 1f
1:
 ldr r0,[r3,#16]
 orrs r0,r4
 pop {r4-r6,pc}
.Llog_ratio70_slow:
 ldr r3,=mk61_m0_log_ratio70_slow
 bx r3
.ltorg
.size mk61_m0_log_ratio70,.-mk61_m0_log_ratio70
