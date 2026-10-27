#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.section .m0_pow_exp_table_transition,"ax",%progbits
.align 2
.global mk61_m0_pow_exp_table_product_flash
.hidden mk61_m0_pow_exp_table_product_flash
.type mk61_m0_pow_exp_table_product_flash,%function
.thumb_func
mk61_m0_pow_exp_table_product_flash:
 push {r0}
 ldr r0,1f
 mov r12,r0
 pop {r0}
 bx r12
 nop
1: .word mk61_m0_pow_exp_table_product
.size mk61_m0_pow_exp_table_product_flash,.-mk61_m0_pow_exp_table_product_flash
#endif
