.syntax unified
.cpu cortex-m0plus
.thumb
.section .product,"ax",%progbits
.balign 2
.global audit_product
.type audit_product,%function
.thumb_func
audit_product:
.incbin "/Users/bolk/Projects/MK61S_MINI/.build/m0-exp-cached-product-20261024/rounded-product.bin"
.size audit_product,.-audit_product
 .section .parent_product,"ax",%progbits
 .balign 2
 .global audit_parent_product
 .type audit_parent_product,%function
 .thumb_func
 audit_parent_product:
 .incbin "/Users/bolk/Projects/MK61S_MINI/.build/m0-exp-cached-product-20261024/parent-rounded-product.bin"
 .size audit_parent_product,.-audit_parent_product
