.syntax unified
.cpu cortex-m0plus
.thumb
.section .m0_qfplib,"ax",%progbits
.global audit_dcmpeq
.type audit_dcmpeq,%function
.thumb_func
audit_dcmpeq:
push {r4,lr}
bl qfp_dcmp
cmp r0,#0
beq 1f
movs r0,#0
pop {r4,pc}
1: movs r0,#1
pop {r4,pc}
.size audit_dcmpeq,.-audit_dcmpeq
.global audit_dcmplt
.type audit_dcmplt,%function
.thumb_func
audit_dcmplt:
push {r4,lr}
bl qfp_dcmp
cmp r0,#0
blt 1f
movs r0,#0
pop {r4,pc}
1: movs r0,#1
pop {r4,pc}
.size audit_dcmplt,.-audit_dcmplt
.global audit_dcmple
.type audit_dcmple,%function
.thumb_func
audit_dcmple:
push {r4,lr}
bl qfp_dcmp
cmp r0,#0
ble 1f
movs r0,#0
pop {r4,pc}
1: movs r0,#1
pop {r4,pc}
.size audit_dcmple,.-audit_dcmple
.global audit_dcmpge
.type audit_dcmpge,%function
.thumb_func
audit_dcmpge:
push {r4,lr}
bl qfp_dcmp
cmp r0,#0
bge 1f
movs r0,#0
pop {r4,pc}
1: movs r0,#1
pop {r4,pc}
.size audit_dcmpge,.-audit_dcmpge
.global audit_dcmpgt
.type audit_dcmpgt,%function
.thumb_func
audit_dcmpgt:
push {r4,lr}
bl qfp_dcmp
cmp r0,#0
bgt 1f
movs r0,#0
pop {r4,pc}
1: movs r0,#1
pop {r4,pc}
.size audit_dcmpgt,.-audit_dcmpgt
.global audit_atan
.type audit_atan,%function
.thumb_func
audit_atan:
push {r4,lr}
movs r2,#0
ldr r3,=0x3ff00000
bl qfp_datan2
pop {r4,pc}
.size audit_atan,.-audit_atan
.ltorg
.section .note.GNU-stack,"",%progbits
