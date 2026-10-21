/* Tail calls preserve ARM EABI, including uldivmod's r0-r3 results.
 * Slot order is shared with the resident, not tied to its symbol addresses. */
.syntax unified
.thumb
#ifndef MK61_RUNTIME_POINTER
#define MK61_RUNTIME_POINTER mk61_system_runtime
#endif
.set runtime_slot, 0
.macro runtime_trampoline name, scratch=r12
.section .text.\name, "ax", %progbits
.global \name
.type \name, %function
.thumb_func
\name:
#if defined(__ARM_ARCH_6M__)
 .ifc \scratch,r3
  /* ISO C services have at most three arguments, including on Thumb-1. */
  ldr r3, =MK61_RUNTIME_POINTER
  ldr r3, [r3]
  ldr r3, [r3, #runtime_slot]
  bx r3
 .else
  push {r4}
  ldr r4, =MK61_RUNTIME_POINTER
  ldr r4, [r4]
  ldr r4, [r4, #runtime_slot]
  mov r12, r4
  pop {r4}
  bx r12
 .endif
#else
  ldr \scratch, =MK61_RUNTIME_POINTER
  ldr \scratch, [\scratch]
  ldr \scratch, [\scratch, #runtime_slot]
  bx \scratch
#endif
.ltorg
.size \name, .-\name
.set runtime_slot, runtime_slot + 4
.endm
#define MK61_RUNTIME(name) runtime_trampoline name
/* ISO C slots take at most three arguments. r3 is caller-clobbered and lets
 * these tails use compact Thumb instructions; EABI helpers retain r0-r3. */
#define MK61_RUNTIME_ISO_C(name, result, ...) runtime_trampoline name, r3
#include "loadable_system_runtime.def"
