/* Same sret ABI as mk61_m0_pow_argument. Integer exponents have sy.low=0
 * and sy.high=n<<s, shift=s+38. Their exact argument is(a80*n)>>6.
 * Five16x11 MULS replace the general17-product path. Other operands
 * retain the original helper, with its original rounding enclosure. */
.section .m0_pow_argument_select,"ax",%progbits
.p2align 2
.hidden mk61_m0_pow_argument_select
regular_func mk61_m0_pow_argument_select
 ldr r1,[sp,#8]
 cmp r1,#0
 bne .Lpow_argument_original
 push {r4,r5,lr}
 ldr r4,[sp,#28]
 subs r4,#48
 cmp r4,#10
 bhi .Lpow_argument_not_integer
 adds r4,#10
 ldr r5,[sp,#24]
 movs r1,r5
 lsrs r1,r4
 lsls r1,r4
 cmp r1,r5
 bne .Lpow_argument_not_integer
 lsrs r5,r4
 mov r12,r0
 uxth r0,r2
 muls r0,r5
 lsrs r4,r0,#16
 uxth r0,r0
 lsrs r2,#16
 muls r2,r5
 adds r2,r4
 lsrs r4,r2,#16
 lsls r2,#16
 orrs r0,r2
 uxth r2,r3
 muls r2,r5
 adds r2,r4
 lsrs r4,r2,#16
 uxth r2,r2
 lsrs r3,#16
 muls r3,r5
 adds r3,r4
 lsrs r4,r3,#16
 lsls r3,#16
 orrs r2,r3
 ldr r3,[sp,#12]
 muls r3,r5
 adds r3,r4
 lsrs r0,#6
 lsls r4,r2,#26
 orrs r0,r4
 lsrs r2,#6
 lsls r4,r3,#26
 orrs r2,r4
 lsrs r3,#6
 mov r4,r12
 movs r5,#0
 str r3,[r4,#0]
 str r5,[r4,#4]
 str r0,[r4,#8]
 str r2,[r4,#12]
 mov r0,r4
 pop {r4,r5,pc}
.Lpow_argument_not_integer:
 pop {r4,r5}
 pop {r1}
 mov lr,r1
.Lpow_argument_original:
 ldr r1,=mk61_m0_pow_argument
 bx r1
 .ltorg
.size mk61_m0_pow_argument_select,.-mk61_m0_pow_argument_select
