_ZN12compact_math4sqrtEd = 0x1016bb01;
__aeabi_d2f = 0x100f753d;
__aeabi_d2iz = 0x100f7761;
__aeabi_d2lz = 0x100f77b1;
__aeabi_d2ulz = 0x100f782d;
__aeabi_dadd = 0x100f79a5;
__aeabi_dcmpeq = 0x100f7581;
__aeabi_dcmpge = 0x100f7675;
__aeabi_dcmpgt = 0x100f76d5;
__aeabi_dcmple = 0x100f7615;
__aeabi_dcmplt = 0x100f75b5;
__aeabi_dcmpun = 0x100f7735;
__aeabi_ddiv = 0x100f7e89;
__aeabi_dmul = 0x100f7cb7;
__aeabi_dsub = 0x100f799b;
__aeabi_f2d = 0x1016b99d;
__aeabi_i2d = 0x100f71d1;
__aeabi_idiv = 0x10083039;
__aeabi_idiv0 = 0x100f798d;
__aeabi_idivmod = 0x10083039;
__aeabi_l2d = 0x100f725d;
__aeabi_ldiv0 = 0x100f798f;
__aeabi_ldivmod = 0x100830d5;
__aeabi_ui2d = 0x100f71e1;
__aeabi_uidiv = 0x100f7961;
__aeabi_uidivmod = 0x100f7961;
__aeabi_ul2d = 0x100f7273;
__aeabi_uldivmod = 0x10083105;
memcpy = 0x100835c1;
memset = 0x100840bf;
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
mk61_m0_pow_argument_select = 0x1017d001;
mk61_m0_pow_dispatch = 0x101612f5;
mk61_m0_pow_exp_product_flash = 0x1016b3b9;
mk61_m0_pow_log_select = 0x10160001;
mk61_m0_pow_negative_integer_dispatch = 0x10161235;
mk61_m0_pow_tiny_or_cr = 0x1016b901;
mk61_m0_product62 = 0x100f7895;
mk61_m0_sqrt = 0x1016bb01;
mk61_m0_sqrt_special = 0x1016ba21;
mk61_m0_trig_inverse_table = 0x10178ae5;
mk61_m0_trig_pi2_product = 0x10178ce5;
mk61_m0_trig_product = 0x10178aed;
pow_integer128_multiply = 0x100f9269;
pow_integer128_square = 0x100f9c9d;
pow_root128_ranged = 0x1014ed69;
pow_rsqrt = 0x10160ef1;
pow_sqrt64_coefficients = 0x1016bc60;
PHDRS { flash PT_LOAD FLAGS(5); entry PT_LOAD FLAGS(5); square PT_LOAD FLAGS(5); rsqrt PT_LOAD FLAGS(5); refine PT_LOAD FLAGS(5); small_y PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(5); }
SECTIONS {
 .pow_entry 0x101614cc : { KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/fixture-candidate.o(.m0_pow_dispatch_extension)) } :entry
 .pow_square 0x10161e00 : { KEEP(*(.m0_pow_square_exact_only)) } :square
 .pow_rsqrt 0x10162800 : { KEEP(*(.m0_pow_rsqrt_fast_only)) } :rsqrt
 .pow_refine 0x10168000 : { KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/RP-candidate-cpp.o(.m0_pow_refine_extension)) } :refine
 .pow_small_y 0x1016ad00 : { KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/RP-candidate-cpp.o(.m0_pow_small_y_cold)) } :small_y
 .pow_flash 0x101b0000 : { *(.m0*) *(.text*) *(.rodata*) } :flash
 .scratch_y 0x20038000 : {
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/RP-candidate-cpp.o(.scratch_y.m0_pow_hot))
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/fixture-candidate.o(.scratch_y.m0_shift_hot))
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-independent-20261025/rebuild/fixture-candidate.o(.scratch_y.m0_pow_hot))
 } :ram
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}
