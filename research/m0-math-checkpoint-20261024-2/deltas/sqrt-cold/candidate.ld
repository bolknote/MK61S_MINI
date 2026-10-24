SECTIONS {
 .sqrt_special 0x1016ba20 : { *(.m0_sqrt_special) }
 .sqrt 0x1016bb00 : { *(.m0_sqrt64_fixed.mk61_m0_sqrt) }
 .conversion 0x10185000 : { *(.text.__aeabi_i2d) }
 /DISCARD/ : { *(*) }
}
