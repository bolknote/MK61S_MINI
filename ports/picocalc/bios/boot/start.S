.syntax unified
.cpu cortex-m3
.thumb
.section .isr_vector,"a",%progbits
.word 0x20004fe0
.word Reset_Handler
.rept 74
.word Default_Handler
.endr
.section .text.Reset_Handler,"ax",%progbits
.global Reset_Handler
.thumb_func
Reset_Handler:
 cpsid i
 ldr r0, =_sidata
 ldr r1, =_sdata
 ldr r2, =_edata
1: cmp r1,r2
 bcs 2f
 ldr r3,[r0],#4
 str r3,[r1],#4
 b 1b
2: ldr r1, =_sbss
 ldr r2, =_ebss
 movs r3,#0
3: cmp r1,r2
 bcs 4f
 str r3,[r1],#4
 b 3b
4: bl boot_main
 b .
.thumb_func
Default_Handler:
 b .
.global boot_jump
.type boot_jump,%function
.thumb_func
boot_jump:
 cpsid i
 ldr r1,=0xe000ed08
 str r0,[r1]
 ldr r1,[r0]
 ldr r0,[r0,#4]
 movs r2,#0
 msr control,r2
 msr msp,r1
 dsb
 isb
 cpsie i
 bx r0
.section .note.GNU-stack,"",%progbits
