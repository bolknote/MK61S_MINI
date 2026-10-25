// Exact same PowInteger128 transform, scheduled for ARMv6-M.
// Struct: high64@0, low64@8, exponent32@16, radius32@20.
.section .m0_pow_square_fixed,"ax",%progbits
.p2align 1
.global pow_integer128_square
.type pow_integer128_square,%function
.thumb_func
.macro pow128_square32
 uxth r2,r0
 lsrs r3,r0,#16
 mov r4,r2
 muls r4,r2
 muls r2,r3
 muls r3,r3
 lsls r1,r2,#17
 lsrs r2,#15
 adds r4,r1
 adcs r3,r2
.endm
pow_integer128_square:
 .fnstart
 .save {r4-r7,lr}
 push {r4-r7,lr}
 .pad #20
 sub sp,#20
 mov r7,r0
 ldr r0,[r7,#0]
 ldr r5,[r7,#4]
 mov r6,r0
 // Exact low32^2 and high32^2, each with three16-bit products.
 pow128_square32
 str r4,[sp,#0]
 str r3,[sp,#4]
 mov r0,r5
 pow128_square32
 str r4,[sp,#8]
 str r3,[sp,#12]
 // Exact low32*high32. Each middle accumulator fits unsigned32.
 uxth r4,r6
 lsrs r6,#16
 uxth r2,r5
 lsrs r5,#16
 mov r0,r4
 muls r0,r2
 muls r2,r6
 lsrs r3,r0,#16
 adds r2,r3
 muls r4,r5
 uxth r3,r2
 adds r4,r3
 muls r5,r6
 lsrs r2,#16
 adds r5,r2
 lsrs r1,r4,#16
 adds r1,r5
 lsls r4,#16
 uxth r0,r0
 orrs r0,r4
 // Add twice the cross product at bit32 of the128-bit square.
 ldr r2,[sp,#4]
 ldr r3,[sp,#8]
 ldr r4,[sp,#12]
 movs r6,#0
 adds r2,r0
 adcs r3,r1
 adcs r4,r6
 adds r2,r0
 adcs r3,r1
 adcs r4,r6
 str r2,[sp,#4]
 str r3,[sp,#8]
 str r4,[sp,#12]
 // Keep the old approximate cross term and its exact radius policy.
 ldr r0,[r7,#8]
 ldr r1,[r7,#12]
 mov r2,r0
 orrs r2,r1
 beq .Lpow128_low_zero
 ldr r2,[r7,#0]
 ldr r3,[r7,#4]
 bl pow_integer128_approx_high64
 ldr r2,[sp,#0]
 ldr r3,[sp,#4]
 ldr r4,[sp,#8]
 ldr r5,[sp,#12]
 movs r6,#0
 adds r2,r0
 adcs r3,r1
 adcs r4,r6
 adcs r5,r6
 adds r2,r0
 adcs r3,r1
 adcs r4,r6
 adcs r5,r6
 ldr r1,[r7,#20]
 lsls r1,#1
 adds r1,#16
 b .Lpow128_normalize
.Lpow128_low_zero:
 ldr r2,[sp,#0]
 ldr r3,[sp,#4]
 ldr r4,[sp,#8]
 ldr r5,[sp,#12]
 ldr r1,[r7,#20]
 cmp r1,#1
 adcs r1,r1                 //2*radius+bool(radius), with uint32 wrap
.Lpow128_normalize:
 ldr r0,[r7,#16]
 lsls r0,#1
 cmp r5,#0
 bmi .Lpow128_upper_half
 lsls r2,#1
 adcs r3,r3
 adcs r4,r4
 adcs r5,r5
 lsls r1,#1
 b .Lpow128_store
.Lpow128_upper_half:
 adds r0,#1
.Lpow128_store:
 str r0,[r7,#16]
 str r1,[r7,#20]
 str r2,[r7,#8]
 str r3,[r7,#12]
 str r4,[r7,#0]
 str r5,[r7,#4]
 add sp,#20
 pop {r4-r7,pc}
.size pow_integer128_square,.-pow_integer128_square
.cantunwind
.fnend
.if (.-pow_integer128_square)>310
 .error "square128 exceeds old resident slot"
.endif
.fill (310-(.-pow_integer128_square))/2,2,0xbf00
.purgem pow128_square32
