#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME && MK61_USE_NATIVE_EABI
.syntax unified
.cpu cortex-m4
.thumb
// Exact scaling by a normal power of two needs no quotient iteration.
// Keep this before the C++ reciprocal path so x/1 and x/2 stay inexpensive.
.section .text.__aeabi_ddiv,"ax",%progbits
.global __aeabi_ddiv
.global __divdf3
.type __aeabi_ddiv,%function
.thumb_func
__aeabi_ddiv:
    cmp r2, #0
    bne mk61_eabi_ddiv_slow
    ubfx r12, r3, #0, #20
    cmp r12, #0
    bne mk61_eabi_ddiv_slow
    push {r4}
    movw r4, #2045
    ubfx r2, r3, #20, #11
    sub r12, r2, #1
    cmp r12, r4
    bhi .Ldiv_fallback
    ubfx r12, r1, #20, #11
    sub r12, r12, #1
    cmp r12, r4
    bhi .Ldiv_scale
    add r12, r12, #1024
    sub r12, r12, r2
    sub r12, r12, #1
    cmp r12, r4
    bhi .Ldiv_out_of_range
    add r12, r12, #1
    bfi r1, r12, #20, #11
    and r3, r3, #0x80000000
    eor r1, r1, r3
    pop {r4}
    bx lr
.Ldiv_out_of_range:
    cmp r12, #0
    blt .Ldiv_scale
    eor r1, r1, r3
    and r1, r1, #0x80000000
    orr r1, r1, #0x7F000000
    orr r1, r1, #0x00F00000
    movs r0, #0
    pop {r4}
    bx lr
.Ldiv_scale:
    pop {r4}
    movs r2, #0
    b mk61_eabi_ddiv_scale
.Ldiv_fallback:
    pop {r4}
    movs r2, #0
    b mk61_eabi_ddiv_slow
.size __aeabi_ddiv, .-__aeabi_ddiv
.thumb_set __divdf3, __aeabi_ddiv
.section .text.__aeabi_uldivmod,"ax",%progbits
.global __aeabi_uldivmod
.type __aeabi_uldivmod,%function
.thumb_func
__aeabi_uldivmod:
    push {r4, lr}
    sub sp, sp, #24
    add r4, sp, #8
    str r4, [sp]
    bl mk61_eabi_divmod64
    ldm r4, {r0, r1, r2, r3}
    add sp, sp, #24
    pop {r4, pc}
.size __aeabi_uldivmod, .-__aeabi_uldivmod
.section .note.GNU-stack,"",%progbits
#endif
