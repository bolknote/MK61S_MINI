.pushsection .m0_rsqrt_local_q8,"ax",%progbits
.syntax unified
.cpu cortex-m0plus
.thumb
.balign 4
.global mk61_m0_pow_rsqrt_local_q8
.hidden mk61_m0_pow_rsqrt_local_q8
.type mk61_m0_pow_rsqrt_local_q8,%function
.global mk61_m0_pow_rsqrt_local_q8_native
.hidden mk61_m0_pow_rsqrt_local_q8_native
.type mk61_m0_pow_rsqrt_local_q8_native,%function
.thumb_func
// Same Q8 formula and frame; early predicates imply the original branch.
// Ordinary AAPCS: preserve R4-R11/SP. No calls, context writes or new tables.
mk61_m0_pow_rsqrt_local_q8:
 push {r4-r7,lr}
 mov r4,r0
 ldr r0,[r4,#28]
 asrs r0,r0,#31
 mvns r0,r0
 b .Lrq8_mask_ready
// Private native entry: incoming C=(Fhigh==0x80000000), established by
// the unique CMP-delta,1/BHI caller guard. PUSH/MOV preserve that C.
// This is NOT the ordinary entry's arbitrary-NZCV contract.
.thumb_func
mk61_m0_pow_rsqrt_local_q8_native:
 push {r4-r7,lr}
 mov r4,r0
 sbcs r0,r0
.Lrq8_mask_ready:
 ldr r5,[r4,#24]             // seed
 ldr r6,[r4,#20]             // Flow
 eors r0,r6
 lsrs r0,r0,#24              // u: Flow if Fhigh80000000, else ~Flow
 mov r12,r0
 muls r6,r5
 lsrs r6,r6,#24
 ldr r0,[r4,#36]
 lsls r0,r0,#22
 lsrs r0,r0,#22
 movs r1,#128
 lsls r1,r1,#2
 subs r1,r1,r0
 lsls r1,r1,#8               // signed target, safe in int32
 mov lr,r1                   // return address remains on the stack
 bmi .Lrq8_negative
.Lrq8_upper_build:
 mov r0,r12
 adds r0,#1
 lsrs r1,r5,#24
 adds r1,#1
 muls r0,r0
 muls r0,r1
 movs r2,#3
 muls r0,r2
 ldr r2,=65535
 adds r0,r0,r2
 lsrs r0,r0,#16
 adds r0,#2                  // nupper + final strict fraction unit
 adds r7,r0,r6              // U0=nupper+fraction+1, eta not yet used
 mov r1,lr
 cmp r7,r1
 ble .Lrq8_down               // product_lower>=0
.Lrq8_eta:
 ldr r0,[r4,#0]
 ldr r1,[r4,#16]
 adds r1,#10
 lsls r0,r1                  // Al
 ldr r1,[r4,#8]              // Bh=high32(seed^2)
 muls r1,r0
 lsrs r3,r1,#24
 mov r1,r5
 muls r1,r5                  // Bl, low32 only
 ldr r2,[r4,#32]             // Ah
 muls r2,r1
 lsrs r2,r2,#24
 adds r3,r3,r2
 lsrs r0,r0,#16
 lsrs r1,r1,#16
 muls r0,r1
 lsrs r0,r0,#24
 adds r3,r3,r0               // eta
 lsrs r0,r5,#24
 muls r0,r3
 lsrs r0,r0,#8
 subs r7,r7,r0
 mov r1,lr
 cmp r7,r1
 ble .Lrq8_down
 mov r0,r12
 muls r0,r0
 lsrs r1,r5,#24
 muls r0,r1
 movs r2,#3
 muls r0,r2
 lsrs r0,r0,#16
 subs r0,#1
 bpl .Lrq8_lower_nonnegative
 movs r0,#0
.Lrq8_lower_nonnegative:
 adds r3,#4
 adds r1,#1
 muls r3,r1
 adds r3,#255
 lsrs r3,r3,#8               // product_upper
 subs r0,r0,r3
 adds r0,r0,r6               // lower
 mov r1,lr
 cmp r0,r1
 blt .Lrq8_decline
.Lrq8_up:
 movs r2,#1
 b .Lrq8_pack
.Lrq8_down:
 movs r2,#0
.Lrq8_pack:
 ldr r0,[r4,#36]
 ldr r1,[r4,#40]
 lsls r3,r1,#22
 lsrs r0,r0,#10
 orrs r0,r3
 lsrs r1,r1,#10              // q >> 10
 adds r0,r0,r2
 movs r2,#0                  // MOVS immediate preserves carry
 adcs r1,r2
 ldr r2,[r4,#12]
 adds r1,r1,r2               // add exact scale high word
 pop {r4-r7,pc}
.Lrq8_decline:
 movs r0,#0
 movs r1,#0
 pop {r4-r7,pc}
.Lrq8_negative:
 lsrs r0,r5,#24
 adds r0,#1
 movs r2,#3
 muls r0,r2
 subs r0,r6,r0
 subs r0,#1
 cmp r0,r1
 bge .Lrq8_up                 // eta<=765; lower>=fraction-3(v+1)-1
 b .Lrq8_upper_build
 .ltorg
.size mk61_m0_pow_rsqrt_local_q8,.-mk61_m0_pow_rsqrt_local_q8
.size mk61_m0_pow_rsqrt_local_q8_native,.-mk61_m0_pow_rsqrt_local_q8_native
.popsection
