.syntax unified
.cpu cortex-m0plus
.thumb

/* Same 16 bit-plane bytes and exact int16 tables as production LUT8.
 * The four bit planes are combined in reverse Horner order. All arithmetic
 * fits int32; this does not change the integer dot product or FP32 order. */
.section .text.interp_dot32,"ax",%progbits
.balign 4
.global interp_dot32
.type interp_dot32,%function
.thumb_func
interp_dot32:
    push {r4,r5,r6,r7,lr}
    lsls r7,r1,#3              /* eight times the input group sum */
    ldr r1,=0xd0000080         /* both interpolators fit one Thumb base */
    movs r6,#0
.macro INTERP_PLANE offset,first=0
    ldr r2,[r0,#\offset]
    lsls r3,r2,#1
    str r3,[r1,#0]            /* INTERP0 ACCUM0: index0/index1 */
    lsrs r2,r2,#15
    str r2,[r1,#64]           /* INTERP1 ACCUM0: index2/index3 */
    ldr r3,[r1,#32]           /* PEEK0, no feedback mutation */
    ldrsh r4,[r3,r6]
    ldr r3,[r1,#36]
    ldrsh r3,[r3,r6]
    adds r4,r4,r3
    ldr r3,[r1,#96]
    ldrsh r3,[r3,r6]
    adds r4,r4,r3
    ldr r3,[r1,#100]
    ldrsh r3,[r3,r6]
    adds r4,r4,r3
.if \first
    mov r5,r4
.else
    lsls r5,r5,#1
    adds r5,r5,r4
.endif
.endm
    INTERP_PLANE 12,1
    INTERP_PLANE 8
    INTERP_PLANE 4
    INTERP_PLANE 0
    subs r0,r5,r7
    pop {r4,r5,r6,r7,pc}
.size interp_dot32,.-interp_dot32
.ltorg

.section .text.packed_dot32,"ax",%progbits
.balign 4
.global packed_dot32
.type packed_dot32,%function
.thumb_func
packed_dot32:
    push {r4,r5,r6,r7,lr}
    mov r12,r8
    movs r6,#128
    lsls r6,r6,#2             /* 512 bytes between subset tables */
    adds r2,r1,r6
    adds r3,r2,r6
    adds r4,r3,r6
    movs r7,#255
    lsls r7,r7,#1             /* even halfword offsets, bits1..8 */
.macro PACKED_PLANE offset,first=0
    ldr r5,[r0,#\offset]
    lsls r6,r5,#1
    ands r6,r7
    ldrsh r6,[r1,r6]
    mov r8,r6
    lsrs r6,r5,#7
    ands r6,r7
    ldrsh r6,[r2,r6]
    add r8,r6
    lsrs r6,r5,#15
    ands r6,r7
    ldrsh r6,[r3,r6]
    add r8,r6
    lsrs r6,r5,#23
    ands r6,r7
    ldrsh r6,[r4,r6]
    add r8,r6
.if \first
    mov lr,r8
.else
    add lr,lr
    add lr,r8
.endif
.endm
    PACKED_PLANE 12,1
    PACKED_PLANE 8
    PACKED_PLANE 4
    PACKED_PLANE 0
    movs r5,#128
    lsls r5,r5,#4
    ldrsh r1,[r1,r5]
    lsls r1,r1,#3
    mov r0,lr
    subs r0,r0,r1
    mov r8,r12
    pop {r4,r5,r6,r7,pc}
.size packed_dot32,.-packed_dot32
.section .note.GNU-stack,"",%progbits
