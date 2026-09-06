/* Tail calls preserve ARM EABI, including uldivmod's r0-r3 results.
 * Slot order is shared with the resident, not tied to its symbol addresses. */
.syntax unified
.thumb
#ifndef MK61_RUNTIME_POINTER
#define MK61_RUNTIME_POINTER mk61_system_runtime
#endif
.set runtime_slot, 0
.macro runtime_trampoline name
.section .text.\name, "ax", %progbits
.global \name
.type \name, %function
.thumb_func
\name:
  ldr r12, =MK61_RUNTIME_POINTER
  ldr r12, [r12]
  ldr r12, [r12, #runtime_slot]
  bx r12
.ltorg
.size \name, .-\name
.set runtime_slot, runtime_slot + 4
.endm
#define MK61_RUNTIME(name) runtime_trampoline name
#include "loadable_system_runtime.def"
