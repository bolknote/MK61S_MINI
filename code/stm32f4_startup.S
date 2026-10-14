/* Project startup for the two qualified Cortex-M4 devices.
 * SystemInit masks old ROM-DFU interrupts before data/BSS are initialized.
 * Only .data/.bss are touched; retained .noinit and the stack stay intact.
 */
#if defined(MK61_NATIVE_RUNTIME) && MK61_NATIVE_RUNTIME
#if !defined(STM32F401xC) && !defined(STM32F411xE)
#error "Owned startup supports STM32F401xC and STM32F411xE"
#endif
.syntax unified
.cpu cortex-m4
.fpu fpv4-sp-d16
.thumb

.section .text.Reset_Handler,"ax",%progbits
.balign 4
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
    ldr sp, =_estack
    bl SystemInit

    ldr r0, =_sidata
    ldr r1, =_sdata
    ldr r2, =_edata
.Lcopy:
    cmp r1, r2
    bcs .Lzero_begin
    ldr r3, [r0], #4
    str r3, [r1], #4
    b .Lcopy
.Lzero_begin:
    ldr r0, =_sbss
    ldr r1, =_ebss
    movs r2, #0
.Lzero:
    cmp r0, r1
    bcs .Lconstruct
    str r2, [r0], #4
    b .Lzero
.Lconstruct:
    ldr r4, =__preinit_array_start
    ldr r5, =__preinit_array_end
    bl .Lcall_array
    ldr r4, =__init_array_start
    ldr r5, =__init_array_end
    bl .Lcall_array
    bl main
    b Default_Handler

/* Constructor callbacks preserve r4/r5 under AAPCS. Keep SP eight-byte aligned.
 * Empty ranges return without reading a callback or consuming stack space.
 */
.Lcall_array:
    cmp r4, r5
    bcs .Larray_empty
    push {r6, lr}
.Larray_next:
    ldr r3, [r4], #4
    blx r3
    cmp r4, r5
    bcc .Larray_next
    pop {r6, pc}
.Larray_empty:
    bx lr
.ltorg
.size Reset_Handler, .-Reset_Handler

.section .text.Default_Handler,"ax",%progbits
.global Default_Handler
.type Default_Handler,%function
.thumb_func
Default_Handler:
    b Default_Handler
.size Default_Handler, .-Default_Handler

/* Strong project handlers override these aliases at the ordinary ARM link. */
#define WEAK_HANDLER(name) .weak name; .thumb_set name, Default_Handler
WEAK_HANDLER(NMI_Handler)
WEAK_HANDLER(HardFault_Handler)
WEAK_HANDLER(MemManage_Handler)
WEAK_HANDLER(BusFault_Handler)
WEAK_HANDLER(UsageFault_Handler)
WEAK_HANDLER(SVC_Handler)
WEAK_HANDLER(DebugMon_Handler)
WEAK_HANDLER(PendSV_Handler)
WEAK_HANDLER(SysTick_Handler)
#define VECTOR_SLOT(index,name) WEAK_HANDLER(name)
#define VECTOR_RESERVED(index)
#include "stm32f4_irq_catalog.inc"
#undef VECTOR_SLOT
#undef VECTOR_RESERVED
#undef WEAK_HANDLER

.section .isr_vector,"a",%progbits
.balign 512
.global g_pfnVectors
.type g_pfnVectors,%object
g_pfnVectors:
    .word _estack, Reset_Handler, NMI_Handler, HardFault_Handler
    .word MemManage_Handler, BusFault_Handler, UsageFault_Handler, 0
    .word 0, 0, 0, SVC_Handler, DebugMon_Handler, 0
    .word PendSV_Handler, SysTick_Handler
#define VECTOR_SLOT(index,name) .word name
#define VECTOR_RESERVED(index) .word 0
#include "stm32f4_irq_catalog.inc"
#undef VECTOR_SLOT
#undef VECTOR_RESERVED
.size g_pfnVectors, .-g_pfnVectors
.section .note.GNU-stack,"",%progbits
#endif
