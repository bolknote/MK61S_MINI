__aeabi_dadd = 0x100f79a5;
__aeabi_ddiv = 0x100f7e89;
__aeabi_dmul = 0x100f7cb7;
__aeabi_dsub = 0x100f799b;
__aeabi_llsl = 0x20038d35;
__aeabi_llsr = 0x20038d55;
__aeabi_uidiv = 0x100f7961;
__aeabi_ul2d = 0x100f7273;
mk61_m0_cr_acos = 0x100ec175;
mk61_m0_cr_asin = 0x100ebcfd;
mk61_m0_cr_atan = 0x100eb945;
mk61_m0_cr_cos = 0x100ef041;
mk61_m0_cr_exp = 0x100ec4d1;
mk61_m0_cr_ln = 0x100f114d;
mk61_m0_cr_log10 = 0x100f1c01;
mk61_m0_cr_pow = 0x100f71c9;
mk61_m0_cr_pow_refined = 0x100f8401;
mk61_m0_cr_sin = 0x100f06e1;
mk61_m0_cr_tan = 0x100effcd;
mk61_m0_log_cube70 = 0x1014d971;
mk61_m0_log_product46 = 0x1014d801;
mk61_m0_log_product54 = 0x1014d8b9;
mk61_m0_log_ratio70 = 0x10160e61;
mk61_m0_math_udiv32 = 0x100f7969;
mk61_m0_pow_argument = 0x20038d95;
mk61_m0_pow_argument_select = 0x1017d001;
mk61_m0_pow_exp_product = 0x20038ee5;
mk61_m0_pow_exp_product_flash = 0x1016b3b9;
mk61_m0_pow_log_select = 0x10160001;
mk61_m0_pow_tiny_or_cr = 0x1016b901;
mk61_m0_product62 = 0x100f7895;
mk61_m0_sqrt = 0x1016bb01;
mk61_m0_trig_inverse_table = 0x10178ae5;
mk61_m0_trig_pi2_product = 0x10178ce5;
mk61_m0_trig_product = 0x10178aed;
pow_integer128_multiply = 0x100f9269;
pow_integer128_square = 0x100f9c9d;
pow_root128_ranged = 0x1014ed69;
SECTIONS {
 . = 0x10185000;
 .text : { *(.text*) *(.m0*) }
 .rodata : { *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}
