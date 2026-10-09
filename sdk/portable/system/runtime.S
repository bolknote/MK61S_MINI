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
  ldr \scratch, =MK61_RUNTIME_POINTER
  ldr \scratch, [\scratch]
  ldr \scratch, [\scratch, #runtime_slot]
  bx \scratch
.ltorg
.size \name, .-\name
.set runtime_slot, runtime_slot + 4
.endm
#define MK61_RUNTIME(name) runtime_trampoline name
/* ISO C slots take at most three arguments. r3 is caller-clobbered and lets
 * these tails use compact Thumb instructions; EABI helpers retain r0-r3. */
#define MK61_RUNTIME_ISO_C(name, result, ...) runtime_trampoline name, r3
#include "loadable_system_runtime.def"
