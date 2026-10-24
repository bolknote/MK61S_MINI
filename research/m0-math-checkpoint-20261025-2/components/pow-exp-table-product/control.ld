__aeabi_dadd = 0x100f79a5;
__aeabi_ddiv = 0x100f7e89;
__aeabi_dmul = 0x100f7cb7;
__aeabi_dsub = 0x100f799b;
__aeabi_uidiv = 0x100f7961;
__aeabi_ul2d = 0x100f7273;
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
PHDRS { s0 PT_LOAD FLAGS(5); s1 PT_LOAD FLAGS(5); s2 PT_LOAD FLAGS(5); s3 PT_LOAD FLAGS(5); s4 PT_LOAD FLAGS(5); s5 PT_LOAD FLAGS(5); s6 PT_LOAD FLAGS(5); s7 PT_LOAD FLAGS(5); s8 PT_LOAD FLAGS(5); s9 PT_LOAD FLAGS(5); s10 PT_LOAD FLAGS(5); s11 PT_LOAD FLAGS(5); s12 PT_LOAD FLAGS(5); s13 PT_LOAD FLAGS(5); s14 PT_LOAD FLAGS(5); s15 PT_LOAD FLAGS(5); s16 PT_LOAD FLAGS(5); s17 PT_LOAD FLAGS(5); s18 PT_LOAD FLAGS(5); s19 PT_LOAD FLAGS(5); s20 PT_LOAD FLAGS(5); s21 PT_LOAD FLAGS(5); s22 PT_LOAD FLAGS(5); s23 PT_LOAD FLAGS(5); s24 PT_LOAD FLAGS(5); s25 PT_LOAD FLAGS(5); s26 PT_LOAD FLAGS(5); s27 PT_LOAD FLAGS(5); s28 PT_LOAD FLAGS(5); s29 PT_LOAD FLAGS(5); s30 PT_LOAD FLAGS(5); s31 PT_LOAD FLAGS(5); s32 PT_LOAD FLAGS(5); s33 PT_LOAD FLAGS(5); s34 PT_LOAD FLAGS(5); s35 PT_LOAD FLAGS(5); s36 PT_LOAD FLAGS(5); s37 PT_LOAD FLAGS(5); s38 PT_LOAD FLAGS(5); s39 PT_LOAD FLAGS(5); s40 PT_LOAD FLAGS(5); s41 PT_LOAD FLAGS(5); s42 PT_LOAD FLAGS(5); s43 PT_LOAD FLAGS(5); s44 PT_LOAD FLAGS(5); s45 PT_LOAD FLAGS(5); s46 PT_LOAD FLAGS(5); s47 PT_LOAD FLAGS(5); s48 PT_LOAD FLAGS(5); s49 PT_LOAD FLAGS(5); s50 PT_LOAD FLAGS(5); s51 PT_LOAD FLAGS(5); s52 PT_LOAD FLAGS(5); s53 PT_LOAD FLAGS(5); s54 PT_LOAD FLAGS(5); s55 PT_LOAD FLAGS(5); s56 PT_LOAD FLAGS(5); s57 PT_LOAD FLAGS(5); s58 PT_LOAD FLAGS(5); s59 PT_LOAD FLAGS(5); s60 PT_LOAD FLAGS(5); s61 PT_LOAD FLAGS(5); s62 PT_LOAD FLAGS(5); s63 PT_LOAD FLAGS(5); s64 PT_LOAD FLAGS(5); s65 PT_LOAD FLAGS(5); s66 PT_LOAD FLAGS(5); s67 PT_LOAD FLAGS(5); s68 PT_LOAD FLAGS(5); s69 PT_LOAD FLAGS(5); s70 PT_LOAD FLAGS(5); s71 PT_LOAD FLAGS(5); s72 PT_LOAD FLAGS(5); s73 PT_LOAD FLAGS(5); s74 PT_LOAD FLAGS(5); s75 PT_LOAD FLAGS(5); s76 PT_LOAD FLAGS(5); s77 PT_LOAD FLAGS(5); s78 PT_LOAD FLAGS(5); s79 PT_LOAD FLAGS(5); s80 PT_LOAD FLAGS(5); s81 PT_LOAD FLAGS(5); s82 PT_LOAD FLAGS(5); s83 PT_LOAD FLAGS(5); s84 PT_LOAD FLAGS(5); s85 PT_LOAD FLAGS(5); s86 PT_LOAD FLAGS(5); s87 PT_LOAD FLAGS(5); s88 PT_LOAD FLAGS(5); s89 PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(5); transition PT_LOAD FLAGS(5); }
SECTIONS {
 .text.unlikely.checked_trig_tan_sixth 0x100e17e4 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.checked_trig_tan_sixth) } :s0
 .text.unlikely.checked_trig_backend 0x100e186e : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.checked_trig_backend) } :s1
 .text.unlikely.atan_inverse_correction.constprop.0 0x100e188c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.atan_inverse_correction.constprop.0) } :s2
 .text._ZN7m0_eabi3jamEyj 0x100e1c00 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi3jamEyj) } :s3
 .text.atan_fast_reciprocal 0x100e1c3e : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.atan_fast_reciprocal) } :s4
 .text.atan_fast_ratio 0x100e1e4a : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.atan_fast_ratio) } :s5
 .text.unlikely.ln_refine 0x100e1e8c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.ln_refine) } :s6
 .text.ln_near_one 0x100e37d8 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.ln_near_one) } :s7
 .text.ln_near_interval 0x100e3cbc : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.ln_near_interval) } :s8
 .text.unlikely.atan_refine 0x100e404c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.atan_refine) } :s9
 .text.atan_fast 0x100e4b50 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.atan_fast) } :s10
 .text.unlikely.checked_trig_tan_midpoint.isra.0 0x100e5220 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.unlikely.checked_trig_tan_midpoint.isra.0) } :s11
 .text._ZN7m0_eabi19divide_significandsEyyRy 0x100e5440 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi19divide_significandsEyyRy) } :s12
 .text.mk61_m0_atan_reduced 0x100e56f0 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_atan_reduced) } :s13
 .text.mk61_m0_ln 0x100e5be0 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_ln) } :s14
 .text.mk61_m0_atan 0x100e60d8 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_atan) } :s15
 .text.__aeabi_lmul 0x100e6444 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.__aeabi_lmul) } :s16
 .text.mk61_m0_udiv32 0x100e644c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_udiv32) } :s17
 .text._ZN7m0_eabi6BinaryILj52ELj11EE9normalizeEyRi 0x100e6494 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE9normalizeEyRi) } :s18
 .text._ZN7m0_eabi6BinaryILj52ELj11EE4packEyiy 0x100e6554 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE4packEyiy) } :s19
 .text._ZN7m0_eabi5fusedEyyy 0x100e65ec : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi5fusedEyyy) } :s20
 .text.mk61_m0_fma 0x100e6b10 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_fma) } :s21
 .text._ZN7m0_eabi6BinaryILj23ELj8EE9normalizeEyRi 0x100e6b22 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj23ELj8EE9normalizeEyRi) } :s22
 .text._ZN7m0_eabi6extendEy 0x100e6b60 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6extendEy) } :s23
 .text.mk61_m0_f2d_slow 0x100e6bb4 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_f2d_slow) } :s24
 .text._ZN7m0_eabi6BinaryILj23ELj8EE4packEyiy 0x100e6bbe : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj23ELj8EE4packEyiy) } :s25
 .text._ZN7m0_eabi6narrowEy 0x100e6c58 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6narrowEy) } :s26
 .text.mk61_m0_d2f_slow 0x100e6ccc : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_d2f_slow) } :s27
 .text._ZN7m0_eabi6BinaryILj52ELj11EE3addEyy 0x100e6cd4 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE3addEyy) } :s28
 .text.mk61_m0_dadd_slow 0x100e6e44 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_dadd_slow) } :s29
 .text._ZN7m0_eabi6BinaryILj52ELj11EE3mulEyy 0x100e6e4c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE3mulEyy) } :s30
 .text.mk61_m0_dmul_slow 0x100e702c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_dmul_slow) } :s31
 .text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy 0x100e7034 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy) } :s32
 .text.mk61_m0_ddiv_slow 0x100e717c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_ddiv_slow) } :s33
 .text._ZN7m0_eabi6BinaryILj52ELj11EE17magnitude_integerEy 0x100e7184 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text._ZN7m0_eabi6BinaryILj52ELj11EE17magnitude_integerEy) } :s34
 .text.__aeabi_d2uiz 0x100e71dc : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.__aeabi_d2uiz) } :s35
 .text.mk61_m0_d2ulz_slow 0x100e71f6 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_d2ulz_slow) } :s36
 .text.mk61_m0_d2lz_slow 0x100e720e : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_d2lz_slow) } :s37
 .text.mk61_m0_d2iz_slow 0x100e7230 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.text.mk61_m0_d2iz_slow) } :s38
 .m0_pow_near_one_refine 0x100f8434 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_near_one_refine) } :s39
 .m0_pow_integer_fixed 0x100f9650 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_integer_fixed) } :s40
 .m0_pow_near_argument_fixed 0x100f9880 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_near_argument_fixed) } :s41
 .rodata._ZN7m0_eabiL19trig94_coefficientsE 0x100fa070 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL19trig94_coefficientsE) } :s42
 .rodata._ZN7m0_eabiL14trig_tan_tableE 0x100fa0d0 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL14trig_tan_tableE) } :s43
 .rodata._ZN7m0_eabiL12trig94_tableE 0x10100590 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL12trig94_tableE) } :s44
 .rodata._ZN7m0_eabiL10log70_highE 0x10105120 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL10log70_highE) } :s45
 .rodata._ZN7m0_eabiL9log70_lowE 0x10105520 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL9log70_lowE) } :s46
 .rodata._ZN7m0_eabiL17refine_atan_tableE 0x10107520 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL17refine_atan_tableE) } :s47
 .rodata._ZN7m0_eabiL16refine_log_tableE 0x1010782c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL16refine_log_tableE) } :s48
 .rodata._ZN7m0_eabiL16refine_exp_tableE 0x1010d82c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL16refine_exp_tableE) } :s49
 .rodata._ZN7m0_eabiL14log_near_tableE 0x1010f030 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL14log_near_tableE) } :s50
 .rodata._ZN7m0_eabiL8trig_pi2E 0x10110030 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL8trig_pi2E) } :s51
 .rodata._ZN7m0_eabiL9exp_tableE 0x10110048 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL9exp_tableE) } :s52
 .rodata._ZN7m0_eabiL16reciprocal_seedsE 0x10111048 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.rodata._ZN7m0_eabiL16reciprocal_seedsE) } :s53
 .m0_math_extension 0x10140000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_math_extension) } :s54
 .m0_math_extension_data 0x10143238 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_math_extension_data) } :s55
 .m0_trig_refine_values_fixed 0x10149a24 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_refine_values_fixed) } :s56
 .m0_trig_refine_fixed 0x1014b904 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_refine_fixed) } :s57
 .m0_trig_cache_ratio 0x1014d050 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_ratio) } :s58
 .m0_trig_cache_clz32 0x1014d436 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_clz32) } :s59
 .m0_trig_cache_clz64 0x1014d478 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_clz64) } :s60
 .m0_trig_cache_low_product 0x1014d4cc : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_low_product) } :s61
 .m0_pow_exact_extension 0x1014e000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_exact_extension) } :s62
 .m0_asin_extension 0x10150d00 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_asin_extension) } :s63
 .m0_asin_refine_extension 0x10156000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_asin_refine_extension) } :s64
 .m0_trig_cache_mulq62 0x1015a6f8 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_mulq62) } :s65
 .m0_trig_cache_atan_ratio 0x1015d686 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cache_atan_ratio) } :s66
 .m0_pow_extension 0x10160024 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_extension) } :s67
 .m0_pow_dispatch_extension 0x10160ef0 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_dispatch_extension) } :s68
 .m0_pow_extension_data 0x101615c8 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_extension_data) } :s69
 .m0_pow_dispatch_ordinary 0x10162200 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_dispatch_ordinary) } :s70
 .m0_pow_refine_extension 0x10168000 : { KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_refine_extension)) } :s71
 .m0_pow_small_y_cold 0x1016ad00 : { KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_small_y_cold)) } :s72
 .m0_trig_argument 0x10170000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_argument) } :s73
 .m0_trig_dispatch 0x10170630 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_dispatch) } :s74
 .m0_trig_small 0x10170878 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_small) } :s75
 .m0_trig_fast_table 0x101712b0 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_fast_table) } :s76
 .m0_trig_table 0x10171674 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_table) } :s77
 .m0_trig_inverse 0x10172a00 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_inverse) } :s78
 .m0_trig_tan_small 0x10172b4c : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_tan_small) } :s79
 .m0_trig_tan_table 0x101730b8 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_tan_table) } :s80
 .m0_trig_tiny_sin 0x10174000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_tiny_sin) } :s81
 .m0_trig_sin70 0x10174044 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_sin70) } :s82
 .m0_trig_cos70 0x101743ac : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_cos70) } :s83
 .m0_exp_core 0x10176000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_exp_core) } :s84
 .m0_exp_endpoints 0x101773ec : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_exp_endpoints) } :s85
 .m0_trig_large 0x10178000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_trig_large) } :s86
 .m0_log_subnormal 0x1017a000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_log_subnormal) } :s87
 .m0_pow_middle 0x1017b000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_middle) } :s88
 .m0_pow_log6 0x1017c000 : { /Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.m0_pow_log6) } :s89
 .scratch_y 0x20038000 : {
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RP-control-cpp.o(.scratch_y.m0_pow_hot))
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RAM-control.o(.scratch_y.m0_shift_hot))
 KEEP(/Users/bolk/Projects/MK61S_MINI/.build/m0-pow-exp-table-product-20261025/RAM-control.o(.scratch_y.m0_pow_hot))
 } :ram
 .table_transition 0x101b0000 : { KEEP(*(.m0_pow_exp_table_transition)) } :transition
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}
