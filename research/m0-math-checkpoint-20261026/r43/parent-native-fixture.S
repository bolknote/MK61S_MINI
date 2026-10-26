.syntax unified
.cpu cortex-m0plus
.thumb
.section .text,"ax",%progbits
.balign 4
.global r43_native_test_entry
.type r43_native_test_entry,%function
.thumb_func
r43_native_test_entry:
 push {r4,lr}
 ldr r2,[r0,#28]
 ldr r3,=0x7fffffff
 subs r2,r2,r3
 cmp r2,#1
 bhi reject
 ldr r3,=268633581
 blx r3
 pop {r4,pc}
reject:
 bkpt #0
 .ltorg
.size r43_native_test_entry,.-r43_native_test_entry
