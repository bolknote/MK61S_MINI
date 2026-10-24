.syntax unified
.cpu cortex-m0plus
.thumb
.macro log_math_function name
 .section .text.seed,"ax",%progbits
 .global \name
 .type \name,%function
 .thumb_func
\name:
.endm
.macro end name
 .size \name,.-\name
.endm
.macro product62_pair a,b
 mov r2,\a
 mov r3,\b
 muls r2,r3
.endm
.macro product62_half1
 mov r3,r2
 lsrs r3,#16
 lsls r2,#16
 adds r5,r2
 adcs r6,r3
.endm
.macro product62_word2
 adds r6,r2
 adcs r7,r4
.endm
.macro product62_half2
 mov r3,r2
 lsrs r3,#16
 lsls r2,#16
 adds r6,r2
 adcs r7,r3
.endm

.macro log_product name,shift,bias
log_math_function \name
 push {r4-r7,lr}
 mov r4,r8
 mov r5,r9
 mov r6,r10
 mov r7,r11
 push {r4-r7}
 uxth r4,r0
 mov r8,r4
 lsrs r0,#16
 mov r9,r0
 mov r10,r1
 uxth r4,r2
 mov r11,r4
 lsrs r2,#16
 mov lr,r2
 uxth r0,r3
 lsrs r1,r3,#16
 movs r4,#0
 movs r6,#0
 movs r7,#0
 product62_pair r8,r0
 mov r5,r2
 product62_pair r9,lr
 adds r5,r2
 adcs r6,r4
 product62_pair r10,r11
 adds r5,r2
 adcs r6,r4
 product62_pair r8,r1
 product62_half1
 product62_pair r9,r0
 product62_half1
 product62_pair r10,lr
 product62_half1
 product62_pair r9,r1
 product62_word2
 product62_pair r10,r0
 product62_word2
 product62_pair r10,r1
 product62_half2
 lsrs r0,r5,#(\shift-32)
 lsls r2,r6,#(64-\shift)
 orrs r0,r2
 lsrs r1,r6,#(\shift-32)
 lsls r3,r7,#(64-\shift)
 orrs r1,r3
 lsls r2,r5,#(65-\shift)
 movs r2,#\bias
 adcs r0,r2
 adcs r1,r4
 pop {r4-r7}
 mov r8,r4
 mov r9,r5
 mov r10,r6
 mov r11,r7
 pop {r4-r7,pc}
end \name
.endm
log_product mk61_m0_log_product46,46,4
