/* Keep additional M0 math out of the previously timed .text/.rodata layout.
 * This address also stays beyond the synthetic load ranges objcopy derives
 * from the SDK's NOLOAD RAM sections when sealing the firmware footer.
 * Both code and tables execute/read directly from flash, with no RAM copy.
 */
SECTIONS {
    /* Preserve every pre-existing math input address after tail extraction. */
    .m0_math_cold_text 0x100e17c0 : {
        . = 0x0;
        *compact_math.cpp.o*(.text._ZN12compact_math3sinEd)
        . = 0xc;
        *compact_math.cpp.o*(.text._ZN12compact_math3cosEd)
        . = 0x18;
        *compact_math.cpp.o*(.text._ZN12compact_math3tanEd)
        . = 0x24;
        *native_eabi_m0.cpp.o*(.text.unlikely.checked_trig_tan_sixth)
        . = 0xae;
        *native_eabi_m0.cpp.o*(.text.unlikely.checked_trig_backend)
        . = 0xcc;
        *native_eabi_m0.cpp.o*(.text.unlikely.atan_inverse_correction.constprop.0)
        . = 0x440;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi3jamEyj)
        . = 0x47e;
        *native_eabi_m0.cpp.o*(.text.atan_fast_reciprocal)
        . = 0x68a;
        *native_eabi_m0.cpp.o*(.text.atan_fast_ratio)
        . = 0x6cc;
        *native_eabi_m0.cpp.o*(.text.unlikely.ln_refine)
        . = 0x2018;
        *native_eabi_m0.cpp.o*(.text.ln_near_one)
        . = 0x24fc;
        *native_eabi_m0.cpp.o*(.text.ln_near_interval)
        . = 0x288c;
        *native_eabi_m0.cpp.o*(.text.unlikely.atan_refine)
        . = 0x3390;
        *native_eabi_m0.cpp.o*(.text.atan_fast)
        . = 0x3a60;
        *native_eabi_m0.cpp.o*(.text.unlikely.checked_trig_tan_midpoint.isra.0)
        . = 0x3c80;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi19divide_significandsEyyRy)
        . = 0x3f30;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_atan_reduced)
        . = 0x4420;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_ln)
        . = 0x4918;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_atan)
        . = 0x4c84;
        *native_eabi_m0.cpp.o*(.text.__aeabi_lmul)
        . = 0x4c8c;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_udiv32)
        . = 0x4cd4;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE9normalizeEyRi)
        . = 0x4d14;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_sqrt_slow)
        . = 0x4d94;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE4packEyiy)
        . = 0x4e2c;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi5fusedEyyy)
        . = 0x5350;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_fma)
        . = 0x5362;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj23ELj8EE9normalizeEyRi)
        . = 0x53a0;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6extendEy)
        . = 0x53f4;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_f2d_slow)
        . = 0x53fe;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj23ELj8EE4packEyiy)
        . = 0x5498;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6narrowEy)
        . = 0x550c;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_d2f_slow)
        . = 0x5514;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE3addEyy)
        . = 0x5684;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_dadd_slow)
        . = 0x568c;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE3mulEyy)
        . = 0x586c;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_dmul_slow)
        . = 0x5874;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE3divEyy)
        . = 0x59bc;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_ddiv_slow)
        . = 0x59c4;
        *native_eabi_m0.cpp.o*(.text._ZN7m0_eabi6BinaryILj52ELj11EE17magnitude_integerEy)
        . = 0x5a1c;
        *native_eabi_m0.cpp.o*(.text.__aeabi_d2uiz)
        . = 0x5a36;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_d2ulz_slow)
        . = 0x5a4e;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_d2lz_slow)
        . = 0x5a70;
        *native_eabi_m0.cpp.o*(.text.mk61_m0_d2iz_slow)
        . = 0x5aa0;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL12cmp_dint_absEPKN14core_m0_shared4TrigES3_)
        . = 0x5b78;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL7cp_dintEPN14core_m0_shared4TrigEPKS1_)
        . = 0x5b98;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL8dint_todEPN14core_m0_shared4TrigE)
        . = 0x5d7c;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN9core_asinL16as_asin_databaseEdd)
        . = 0x5e2c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_logL7cp_dintEPN14core_m0_shared3LogEPKS1_)
        . = 0x5e4e;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_logL8cmp_dintEPKN14core_m0_shared3LogES3_)
        . = 0x5eb4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_logL8dint_todEPN14core_m0_shared3LogE)
        . = 0x5f58;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL7cp_dintEPNS_8dint64_tEPKS0_)
        . = 0x5f76;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL7cp_qintEPNS_8qint64_tEPKS0_)
        . = 0x5fa4;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_expL15as_exp_databaseEdd)
        . = 0x6074;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL5a_mulEPdS0_dd)
        . = 0x60bc;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL5d_mulEPdS0_dddd)
        . = 0x6100;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL5s_mulEPdS0_ddd)
        . = 0x6134;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL10evalPSfastEPdS0_dddd)
        . = 0x6214;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL10evalPCfastEPdS0_dd)
        . = 0x62d0;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN9core_atanL9muldd_accEddddPd)
        . = 0x6370;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL6set_ddEPdS0_yy)
        . = 0x6510;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL10dint_fromdEPN14core_m0_shared4TrigEd)
        . = 0x65a0;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL9normalizeEPN14core_m0_shared4TrigE)
        . = 0x663a;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL12cmp_dint_absEPKNS_8dint64_tES2_)
        . = 0x6704;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN9core_atanL15as_atan_refine2Edd)
        . = 0x6d64;
        *native_eabi_m0_cr.cpp.o*(.text._Z14mk61_m0_wide32mm)
        . = 0x6d90;
        *native_eabi_m0_cr.cpp.o*(.text._Zml15mk61_m0_uint128S_)
        . = 0x6e3e;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_logL8mul_dintEPN14core_m0_shared3LogEPKS1_S4_)
        . = 0x7034;
        *native_eabi_m0_cr.cpp.o*(.text._ZN10core_log10L8mul_dintEPN14core_m0_shared3LogEPKS1_S4_)
        . = 0x722a;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL8mul_qintEPNS_8qint64_tEPKS0_S3_)
        . = 0x77c6;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11mul_qint_41EPNS_8qint64_tEPKS0_S3_)
        . = 0x7a70;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL6reduceEPN14core_m0_shared4TrigE)
        . = 0x7f4c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL10mul_qint_2EPNS_8qint64_tExPKS0_.constprop.0)
        . = 0x8240;
        *native_eabi_m0_cr.cpp.o*(.text._Z10core_rounddi)
        . = 0x8354;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sinL11reduce_fastEPdS0_dS0_)
        . = 0x86bc;
        *native_eabi_m0_cr.cpp.o*(.text._Z10core_ctzlly)
        . = 0x86d8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN9core_asinL16roundeven_finiteEd)
        . = 0x8758;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN9core_acosL14as_acos_refineEdd)
        . = 0x8f24;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_expL15as_exp_accurateEd)
        . = 0x9464;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL6is_intEd)
        . = 0x947c;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN9core_asinL14as_asin_refineEdd)
        . = 0x9ad8;
        *native_eabi_m0_cr.cpp.o*(.text._ZlsIiLi0EE15mk61_m0_uint128S0_T_)
        . = 0x9b6c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL14mul_dint_int64EPNS_8dint64_tEPKS0_x.constprop.0)
        . = 0x9d70;
        *native_eabi_m0_cr.cpp.o*(.text._ZN9core_atan7cr_atanEd)
        . = 0xa184;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_atan)
        . = 0xa18c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN9core_asin7cr_asinEd)
        . = 0xa53c;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_asin)
        . = 0xa544;
        *native_eabi_m0_cr.cpp.o*(.text._ZN9core_acos7cr_acosEd)
        . = 0xa9b4;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_acos)
        . = 0xa9bc;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_exp6cr_expEd)
        . = 0xad10;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_exp)
        . = 0xad18;
        *native_eabi_m0_cr.cpp.o*(.text._ZrsIyLi0EE15mk61_m0_uint128S0_T_)
        . = 0xada8;
        *native_eabi_m0_cr.cpp.o*(.text._ZrsIiLi0EE15mk61_m0_uint128S0_T_)
        . = 0xae30;
        *native_eabi_m0_cr.cpp.o*(.text._ZlsIyLi0EE15mk61_m0_uint128S0_T_)
        . = 0xaecc;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL8add_dintEPN14core_m0_shared4TrigEPKS1_S4_)
        . = 0xb2c0;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_cosL8add_dintEPN14core_m0_shared4TrigEPKS1_S4_)
        . = 0xb6b4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_tanL8add_dintEPN14core_m0_shared4TrigEPKS1_S4_)
        . = 0xbaa8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL8add_dintEPNS_8dint64_tEPKS0_S3_)
        . = 0xbe9c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11add_qint_22EPNS_8qint64_tEPKS0_S3_)
        . = 0xc2f0;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL8add_qintEPNS_8qint64_tEPKS0_S3_)
        . = 0xcefc;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL11mul_dint_21EPN14core_m0_shared4TrigEPKS1_S4_)
        . = 0xd014;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely._ZN8core_sinL8mul_dintEPN14core_m0_shared4TrigEPKS1_S4_)
        . = 0xd1ac;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_cos6cr_cosEd)
        . = 0xd880;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_cos)
        . = 0xd888;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_tanL8inv_dintEPN14core_m0_shared4TrigES2_)
        . = 0xdba4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_tanL12tan_accurateEd)
        . = 0xdf30;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_tan6cr_tanEd)
        . = 0xe80c;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_tan)
        . = 0xe814;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_sin6cr_sinEd)
        . = 0xef20;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_sin)
        . = 0xef28;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_logL8add_dintEPN14core_m0_shared3LogEPKS1_S4_)
        . = 0xf264;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_log6cr_logEd)
        . = 0xf98c;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_ln)
        . = 0xf994;
        *native_eabi_m0_cr.cpp.o*(.text._ZN10core_log10L8add_dintEPN14core_m0_shared3LogEPKS1_S4_)
        . = 0xfcd0;
        *native_eabi_m0_cr.cpp.o*(.text._ZN10core_log108cr_log10Ed)
        . = 0x10440;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_log10)
        . = 0x10448;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11mul_dint_11EPNS_8dint64_tEPKS0_S3_)
        . = 0x104f8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11add_dint_11EPNS_8dint64_tEPKS0_S3_)
        . = 0x10734;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11mul_dint_21EPNS_8dint64_tEPKS0_S3_)
        . = 0x10842;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL8mul_dintEPNS_8dint64_tEPKS0_S3_)
        . = 0x109d0;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL11mul_qint_11EPNS_8qint64_tEPKS0_S3_)
        . = 0x10a88;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE9normalizeEyRyRi)
        . = 0x10ae8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE5timesERKNS1_1BEy)
        . = 0x10b68;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE3addERKNS1_1BES4_)
        . = 0x10b98;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE7compareERKNS1_1BES4_)
        . = 0x10bba;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE8subtractERKNS1_1BES4_)
        . = 0x10bf8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE9shifted64ERKNS1_1BEj)
        . = 0x10c64;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE10differenceERKNS1_1BES4_)
        . = 0x10c9c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE9normalizeEyRyRi)
        . = 0x10cfc;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE5timesERKNS1_1BEy)
        . = 0x10d7c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE3addERKNS1_1BES4_)
        . = 0x10dac;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE7compareERKNS1_1BES4_)
        . = 0x10dce;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE8subtractERKNS1_1BES4_)
        . = 0x10e0c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE9shifted64ERKNS1_1BEj)
        . = 0x10e78;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE10differenceERKNS1_1BES4_)
        . = 0x10eae;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE12word_productEmm)
        . = 0x10eda;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE9incrementERKNS1_1BE)
        . = 0x10f02;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE7productERKNS1_1BES4_b)
        . = 0x10fb0;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE6divideERKNS1_1BEmb)
        . = 0x11014;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE12log_mantissaEy)
        . = 0x111c4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE12exp_endpointERKNS1_1SE)
        . = 0x11318;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE9any_belowERKNS1_1BEj)
        . = 0x1135e;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE5shiftERKNS1_1BEib)
        . = 0x1144c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE7roundedERKNS1_1BEi)
        . = 0x11518;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE14exact_boundaryEyyRy)
        . = 0x1185c;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj512EE8evaluateEyyRy)
        . = 0x11c74;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE12word_productEmm)
        . = 0x11ca0;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE9incrementERKNS1_1BE)
        . = 0x11cc8;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE7productERKNS1_1BES4_b)
        . = 0x11d78;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE6divideERKNS1_1BEmb)
        . = 0x11ddc;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE12log_mantissaEy)
        . = 0x11fc4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE12exp_endpointERKNS1_1SE)
        . = 0x12134;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE9any_belowERKNS1_1BEj)
        . = 0x1217a;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE5shiftERKNS1_1BEib)
        . = 0x12268;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE7roundedERKNS1_1BEi)
        . = 0x12330;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE14exact_boundaryEyyRy)
        . = 0x12674;
        *native_eabi_m0_cr.cpp.o*(.text._ZN15m0_pow_interval5FixedILj1024EE8evaluateEyyRy)
        . = 0x12b5c;
        *native_eabi_m0_cr.cpp.o*(.text.unlikely.mk61_m0_pow_rescue)
        . = 0x12bc4;
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_pow6cr_powEdd)
        /* The extracted body and exactness test fit inside the old pow slot.
         * The next fixed input offset rejects any accidental overlap. */
        . = ALIGN(4);
        *(.m0_pow_accurate)
        *native_eabi_m0_cr.cpp.o*(.text._ZN8core_powL8is_exactEdd)
        . = 0x15a08;
        *native_eabi_m0_cr.cpp.o*(.text.mk61_m0_cr_pow)
        . = 0x15a10;
        *native_eabi_m0.S.o*(.text.__aeabi_i2d)
        . = 0x15d7c;
        *native_eabi_m0.S.o*(.text.__aeabi_d2f)
        . = 0x15dc0;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmpeq)
        . = 0x15df4;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmplt)
        . = 0x15e54;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmple)
        . = 0x15eb4;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmpge)
        . = 0x15f14;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmpgt)
        . = 0x15f74;
        *native_eabi_m0.S.o*(.text.__aeabi_dcmpun)
        . = 0x15fa0;
        *native_eabi_m0.S.o*(.text.__aeabi_d2iz)
        . = 0x15ff0;
        *native_eabi_m0.S.o*(.text.__aeabi_d2lz)
        . = 0x1606c;
        *native_eabi_m0.S.o*(.text.__aeabi_d2ulz)
        . = 0x160d4;
        *native_eabi_m0.S.o*(.text.mk61_m0_product62)
        . = 0x161a0;
        *native_eabi_m0.S.o*(.text.__aeabi_uidiv)
        . = 0x161a8;
        *native_eabi_m0.S.o*(.text.mk61_m0_math_udiv32)
        . = 0x161cc;
        *native_eabi_m0.S.o*(.text.__aeabi_idiv0)
        . = 0x161ce;
        *native_eabi_m0.S.o*(.text.__aeabi_ldiv0)
        . = 0x161d0;
        *native_eabi_m0_rp2040.S.o*(.text.mk61_rp2040_arithmetic)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    /* Do not move the pre-existing long-call veneer group after adding code. */
    .m0_pow_new_cold 0x100f8400 : {
        *compact_math.cpp.o*(.text*)
        *native_eabi_m0.cpp.o*(.text*)
        *native_eabi_m0_cr.cpp.o*(.text*)
        *native_eabi_m0.S.o*(.text*)
        *native_eabi_m0_rp2040.S.o*(.text*)
        *(.m0_pow_near_one_refine)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_math_cold_text) + SIZEOF(.m0_math_cold_text) <= ADDR(.m0_pow_new_cold),
           "Existing math veneers overlap new pow helpers")
    ASSERT(ADDR(.m0_pow_new_cold) + SIZEOF(.m0_pow_new_cold) <= 0x100fa070,
           "New pow helpers overlap existing constants")
    /* Keep the near-one refinement and its integer-domain decline at
     * the qualified V101 indices. Pack the new square into the unused gap;
     * padding places the common long-call veneers at their old index span. */
    ASSERT(ADDR(.m0_pow_new_cold) + SIZEOF(.m0_pow_new_cold) <= 0x100f9650,
           "Packed pow helpers overlap fixed near-one entries")
    .m0_pow_near_fixed 0x100f9650 : {
        __m0_pow_integer_fixed_begin = ABSOLUTE(.);
        *(.m0_pow_integer_fixed)
        __m0_pow_near_argument_fixed_begin = ABSOLUTE(.);
        *(.m0_pow_near_argument_fixed)
        . = ALIGN(4);
        *(.m0_pow_square_fixed)
        . = 0x980;
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(__m0_pow_integer_fixed_begin == 0x100f9650,
           "Fixed integer-domain entry moved")
    ASSERT(__m0_pow_near_argument_fixed_begin == 0x100f9880,
           "Fixed near-one argument entry moved")
    ASSERT(ADDR(.m0_pow_near_fixed) + SIZEOF(.m0_pow_near_fixed) <= 0x100fa070,
           "Fixed near-one code overlaps existing constants")
    .m0_math_cold_data 0x100fa070 : {
        . = 0x0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL19trig94_coefficientsE)
        . = 0x60;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL14trig_tan_tableE)
        . = 0x6520;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL12trig94_tableE)
        . = 0xb0b0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL10log70_highE)
        . = 0xb4b0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL9log70_lowE)
        . = 0xd4b0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL17refine_atan_tableE)
        . = 0xd7bc;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL16refine_log_tableE)
        . = 0x137bc;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL16refine_exp_tableE)
        . = 0x14fc0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL14log_near_tableE)
        . = 0x15fc0;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL8trig_pi2E)
        . = 0x15fd8;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL9exp_tableE)
        . = 0x16fd8;
        *native_eabi_m0.cpp.o*(.rodata._ZN7m0_eabiL16reciprocal_seedsE)
        . = 0x170d8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_pow6cr_powEddE3err)
        . = 0x170e8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_powL8is_exactEddE4xmax)
        . = 0x171f8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_powL5log_1EPdS0_dE2cm)
        . = 0x17208;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL2T2E)
        . = 0x17608;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL2T1E)
        . = 0x17a08;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL8_LOG_INVE)
        . = 0x18568;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL8_INVERSEE)
        . = 0x18b18;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL3Q_3E)
        . = 0x18de8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL3P_3E)
        . = 0x19148;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL4T2_3E)
        . = 0x19d48;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL4T1_3E)
        . = 0x1a948;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_LOG_INV_3_2E)
        . = 0x1c178;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_LOG_INV_3_1E)
        . = 0x1d2b8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_INVERSE_3_2E)
        . = 0x1eae8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_INVERSE_3_1E)
        . = 0x1fc28;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL6ZERO_QE)
        . = 0x1fc58;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL10LOG2_INV_QE)
        . = 0x1fc88;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL6LOG2_QE)
        . = 0x1fcb8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL7M_ONE_QE)
        . = 0x1fce8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL3Q_2E)
        . = 0x1fde8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL3P_2E)
        . = 0x1ff08;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL4T2_2E)
        . = 0x20708;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL4T1_2E)
        . = 0x20f08;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_LOG_INV_2_2E)
        . = 0x21f28;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_LOG_INV_2_1E)
        . = 0x22aa8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_INVERSE_2_2E)
        . = 0x23ac8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL12_INVERSE_2_1E)
        . = 0x24648;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL4ZEROE)
        . = 0x24668;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL8LOG2_INVE)
        . = 0x24688;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_powL5M_ONEE)
        . = 0x246a8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN15m0_pow_intervalL8ln2_1024E)
        . = 0x24728;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_expL15as_exp_accurateEdE2ch)
        . = 0x24798;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_expL2t1E)
        . = 0x24b98;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_expL2t0E)
        . = 0x24f98;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_expL15as_exp_databaseEddE2s2)
        . = 0x24fa8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_expL2dbE)
        . = 0x25140;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN10core_log108cr_log10EdE5pow10)
        . = 0x25240;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN10core_log10L8_LOG_INVE)
        . = 0x268f0;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN10core_log10L8_INVERSEE)
        . = 0x27448;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN10core_log10L4ZEROE)
        . = 0x27468;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN10core_log10L14ONE_OVER_LOG10E)
        . = 0x27488;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN10core_log10L5M_ONEE)
        . = 0x274a8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_logL11cr_log_fastEPdS0_iNS_6d64u64EE2cm)
        . = 0x274b8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_logL11cr_log_fastEPdS0_iNS_6d64u64EE2cy)
        . = 0x274c8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL8_LOG_INVE)
        . = 0x28b78;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL8_INVERSEE)
        . = 0x296d0;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL3P_2E)
        . = 0x29870;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL10_LOG_INV_2E)
        . = 0x2b670;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL10_INVERSE_2E)
        . = 0x2d470;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL4ZEROE)
        . = 0x2d490;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_logL5M_ONEE)
        . = 0x2d4b0;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_acosL14as_acos_refineEddE1c)
        . = 0x2d500;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_acos7cr_acosEdE3off)
        . = 0x2d520;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_acos7cr_acosEdE2cc)
        . = 0x2dd60;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_asinL16as_asin_databaseEddE2db)
        . = 0x2e018;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_asinL14as_asin_refineEddE1c)
        . = 0x2e068;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_asinL14as_asin_refineEddE1s)
        . = 0x2e278;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_asin7cr_asinEdE3off)
        . = 0x2e298;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_asin7cr_asinEdE2cc)
        . = 0x2ead8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_atanL15as_atan_refine2EddE2db)
        . = 0x2ebf8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN9core_atanL15as_atan_refine2EddE2ch)
        . = 0x2ec28;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN9core_atanL1cE)
        . = 0x2ece8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN9core_atanL1AE)
        . = 0x2f4f8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_tanL12tan_accurateEdE10exceptions)
        . = 0x2f528;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL2PCE)
        . = 0x2f5e8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL2PSE)
        . = 0x2f6a8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL4TinvE)
        . = 0x2fea8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL5MAGICE)
        . = 0x2fec8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL3ONEE)
        . = 0x2fee8;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_tanL4ZEROE)
        . = 0x2ff08;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_cosL12cos_accurateEdE10exceptions)
        . = 0x2ff80;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_cosL2PCE)
        . = 0x30040;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_cosL2PSE)
        . = 0x30100;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_cosL5MAGICE)
        . = 0x30120;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_cosL4ZEROE)
        . = 0x30140;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_sinL12sin_accurateEdE10exceptions)
        . = 0x30170;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZZN8core_sinL8sin_fastEPdS0_dE3sgn)
        . = 0x30180;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL2SCE)
        . = 0x31980;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL2PCE)
        . = 0x31a40;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL2PSE)
        . = 0x31b00;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL1CE)
        . = 0x33b00;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL1SE)
        . = 0x35b00;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL1TE)
        . = 0x35ba0;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL5MAGICE)
        . = 0x35bc0;
        *native_eabi_m0_cr.cpp.o*(.rodata._ZN8core_sinL4ZEROE)
        . = 0x35be0;
        *native_eabi_m0_cr.cpp.o*(.rodata)
        . = 0x35bf0;
        *native_eabi_m0.cpp.o*(.rodata*)
        *native_eabi_m0_cr.cpp.o*(.rodata*)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(LOADADDR(.data) + SIZEOF(.data) <= ADDR(.m0_math_cold_text),
           "Platform firmware overlaps fixed math code")
    ASSERT(ADDR(.m0_math_cold_text) + SIZEOF(.m0_math_cold_text) <= ADDR(.m0_math_cold_data),
           "Fixed math code overlaps existing constants")
    ASSERT(ADDR(.m0_math_cold_data) + SIZEOF(.m0_math_cold_data) <= 0x10140000,
           "Fixed math constants overlap math hot sections")
    .m0_math_extension 0x10140000 : {
        *(.m0_math_extension)
        *(.m0_math_extension_data)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    /* Keep these leaf product helpers disjoint from the fixed log10
     * hot path in cache index space. Grouping the unchanged bodies also
     * decouples their placement from future platform text growth. */
    /* Stable indices for the rare tangent refinement, independent of platform text growth. */
    .m0_trig_refine_fixed 0x10149a24 : {
        *(.m0_trig_refine_values_fixed)
        . = ALIGN(4);
        *(.m0_trig_refine_fixed)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_math_extension) + SIZEOF(.m0_math_extension) <= ADDR(.m0_trig_refine_fixed),
           "Math tables overlap stable tangent refinement")
    ASSERT(ADDR(.m0_trig_refine_fixed) + SIZEOF(.m0_trig_refine_fixed) <= 0x1014d800,
           "Stable tangent refinement overlaps log product helpers")
    /* Preserve the successful old indices of the shared tangent helpers.
     * One output section lets the linker append long-call veneers after
     * the last helper without moving the following function entries. */
    .m0_trig_support_fixed 0x1014d050 : {
        *(.m0_trig_cache_ratio)
        . = 0x3e6;
        *(.m0_trig_cache_clz32)
        . = 0x428;
        *(.m0_trig_cache_clz64)
        . = 0x47c;
        *(.m0_trig_cache_low_product)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_trig_refine_fixed) + SIZEOF(.m0_trig_refine_fixed) <= ADDR(.m0_trig_support_fixed),
           "Tangent refinement overlaps support functions")
    ASSERT(ADDR(.m0_trig_support_fixed) + SIZEOF(.m0_trig_support_fixed) <= 0x1014d800,
           "Tangent support overlaps log product helpers")
    .m0_log_product_extension 0x1014d800 : {
        *(.m0_log_product_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_math_extension) + SIZEOF(.m0_math_extension) <= ADDR(.m0_log_product_extension),
           "M0 tables overlap relocated log product helpers")
    ASSERT(SIZEOF(.m0_log_product_extension) <= 0x200,
           "M0 log product helper group exceeds512bytes")
    /* Existing gap: keep the same root code at cache index0x1a60. */
    .m0_pow_root64_fixed 0x1014de60 : {
        *(.m0_sqrt64_fixed.root64)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_log_product_extension) + SIZEOF(.m0_log_product_extension) <= ADDR(.m0_pow_root64_fixed),
           "Log products overlap the fixed root helper")
    ASSERT(ADDR(.m0_pow_root64_fixed) + SIZEOF(.m0_pow_root64_fixed) <= 0x1014e000,
           "Fixed root helper overlaps exact pow")
    .m0_pow_exact_extension 0x1014e000 : {
        *(.m0_pow_exact_extension)
        *(.m0_pow_root_prefix)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.m0_pow_exact_extension) <= 0x2000,
           "Exact pow endpoint comparison exceeds its8KiB slot")
    ASSERT(ADDR(.m0_log_product_extension) + SIZEOF(.m0_log_product_extension) <= ADDR(.m0_pow_exact_extension),
           "Log product helpers overlap exact pow endpoint comparison")
    .m0_pow_boundary_fixed 0x10150000 : {
        *(.m0_pow_boundary_exact)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.m0_pow_boundary_fixed) <= 0xd00,
           "Pow boundary evaluator overlaps asin")
    .m0_pow_tail_fixed 0x10150280 : {
        *(.m0_pow_tail_extra)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_pow_tail_fixed) + SIZEOF(.m0_pow_tail_fixed) <= 0x10150d00,
           "Pow tail overlaps asin")
    .m0_asin_extension 0x10150d00 : {
        *(.m0_asin_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_asin_refine_extension 0x10156000 : {
        *(.m0_asin_refine_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_trig_mulq62_fixed 0x1015a6f8 : {
        *(.m0_trig_cache_mulq62)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_trig_ratio_fixed 0x1015d686 : {
        *(.m0_trig_cache_atan_ratio)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_asin_refine_extension) + SIZEOF(.m0_asin_refine_extension) <= ADDR(.m0_trig_mulq62_fixed),
           "Asin refinement overlaps shared multiplication")
    ASSERT(ADDR(.m0_trig_mulq62_fixed) + SIZEOF(.m0_trig_mulq62_fixed) <= ADDR(.m0_trig_ratio_fixed),
           "Shared multiplication overlaps tangent quotient")
    ASSERT(ADDR(.m0_trig_ratio_fixed) + SIZEOF(.m0_trig_ratio_fixed) <= 0x10160000,
           "Tangent quotient overlaps pow")
    .m0_pow_extension 0x10160000 : {
        *(.m0_pow_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    /* A two-way16KiB XIP cache has an8KiB index period. Pack the
     * pow helpers and inverse-root seeds into one aligned index span,
     * avoiding conflicts between different parts of the same hot code. */
    .m0_pow_dispatch_extension ALIGN(ADDR(.m0_pow_extension) + SIZEOF(.m0_pow_extension), 16) : {
        *(.m0_pow_dispatch_extension)
        *(.m0_pow_extension_data)
        *(.m0_pow_argument_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_pow_refine_extension 0x10168000 : {
        *(.m0_pow_refine_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_pow_small_y_cold 0x1016ad00 : {
        *(.m0_pow_small_y_cold)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_pow_refine_extension) + SIZEOF(.m0_pow_refine_extension) <= ADDR(.m0_pow_small_y_cold),
           "Pow refinement overlaps small-y interval path")
    ASSERT(ADDR(.m0_pow_small_y_cold) + SIZEOF(.m0_pow_small_y_cold) <= 0x1016b900,
           "Small-y interval path overlaps magnitude helper")
    /* Existing free gap; no old function, table or RAM allocation moves. */
    .m0_pow_tiny_cold 0x1016b900 : {
        *(.m0_pow_tiny_cold)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_pow_refine_extension) + SIZEOF(.m0_pow_refine_extension) <= ADDR(.m0_pow_tiny_cold),
           "Pow refinement overlaps tiny-exponent cold edge")
    ASSERT(ADDR(.m0_pow_tiny_cold) + SIZEOF(.m0_pow_tiny_cold) <= 0x1016b99c,
           "Tiny-exponent cold edge overlaps stable conversion")
    .m0_conversion_fixed 0x1016b99c : {
        *(.m0_conversion_fixed.*)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_sqrt64_fixed 0x1016bb00 : {
        *(.m0_sqrt64_fixed.*)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_pow_refine_extension) + SIZEOF(.m0_pow_refine_extension) <= ADDR(.m0_conversion_fixed),
           "Pow refinement overlaps stable conversion")
    ASSERT(ADDR(.m0_conversion_fixed) + SIZEOF(.m0_conversion_fixed) <= ADDR(.m0_sqrt64_fixed),
           "Stable conversion overlaps square root")
    ASSERT(ADDR(.m0_sqrt64_fixed) + SIZEOF(.m0_sqrt64_fixed) <= 0x10170000,
           "Stable square root overlaps trig core")
    /* Keep the shared argument/dispatcher below cache offset0xa00.
     * Sin/cos then use the rest of this single8KiB index span. Tan
     * instead uses its own code at offset0xa00, disjoint from the shared
     * part. No code is copied to main RAM and no table is added. */
    .m0_trig_core_extension 0x10170000 : {
        *(.m0_trig_argument)
        *(.m0_trig_dispatch)
        __m0_trig_shared_end = ABSOLUTE(.);
        *(.m0_trig_small)
        *(.m0_trig_fast_table)
        *(.m0_trig_table)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_trig_tangent_extension 0x10172a00 : {
        *(.m0_trig_inverse)
        *(.m0_trig_tan_small)
        *(.m0_trig_tan_table)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(__m0_trig_shared_end <= ADDR(.m0_trig_core_extension) + 0xa00,
           "Shared trig argument/dispatcher overlap tangent cache indices")
    ASSERT(SIZEOF(.m0_trig_core_extension) <= 0x2000,
           "Sin/cos hot code exceeds one8KiB cache index span")
    ASSERT(SIZEOF(.m0_trig_tangent_extension) <= 0xe00,
           "Tangent hot code overlaps the fixed log-product cache indices")
    ASSERT(ADDR(.m0_pow_refine_extension) + SIZEOF(.m0_pow_refine_extension) <= ADDR(.m0_trig_core_extension),
           "Pow refinement overlaps fixed trig hot code")
    ASSERT(ADDR(.m0_trig_tangent_extension) + SIZEOF(.m0_trig_tangent_extension) <= 0x10180000,
           "Trig hot code overlaps isolated comparison reference")
    .m0_trig_small_refine_extension 0x10174000 : {
        *(.m0_trig_tiny_sin)
        *(.m0_trig_sin70)
        *(.m0_trig_cos70)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_trig_tangent_extension) + SIZEOF(.m0_trig_tangent_extension) <= ADDR(.m0_trig_small_refine_extension),
           "Tangent code overlaps small trig refinement")
    ASSERT(SIZEOF(.m0_trig_small_refine_extension) <= 0x800,
           "Small trig refinement exceeds its2KiB slot")
    /* Keep the exp entry and refinement in a single XIP index span.
     * No new arithmetic, constants or RAM are introduced. */
    .m0_exp_core_extension 0x10176000 : {
        *(.m0_exp_core)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_trig_small_refine_extension) + SIZEOF(.m0_trig_small_refine_extension) <= ADDR(.m0_exp_core_extension),
           "Small trig refinement overlaps exp core")
    ASSERT(SIZEOF(.m0_exp_core_extension) <= 0x2000,
           "Exp code exceeds one8KiB cache index span")
    ASSERT(ADDR(.m0_exp_core_extension) + SIZEOF(.m0_exp_core_extension) <= 0x10180000,
           "Exp code overlaps isolated comparison reference")
    ASSERT(LOADADDR(.data) + SIZEOF(.data) <= ADDR(.m0_math_extension),
           "Main firmware overlaps the M0 math extension")
    ASSERT(SIZEOF(.m0_math_extension) <= 0x10000,
           "M0 log10 extension overlaps asin extension")
    ASSERT(ADDR(.m0_asin_extension) + SIZEOF(.m0_asin_extension) <= ADDR(.m0_asin_refine_extension),
           "M0 asin hot path overlaps refinement")
    ASSERT(SIZEOF(.m0_asin_refine_extension) <= 0xa000,
           "M0 asin refinement overlaps pow extension")
    ASSERT(ADDR(.m0_pow_dispatch_extension) + SIZEOF(.m0_pow_dispatch_extension) <= ADDR(.m0_pow_extension) + 0x2000,
           "Hot M0 pow code and seeds exceed one8KiB cache index span")
    ASSERT(ADDR(.m0_pow_dispatch_extension) + SIZEOF(.m0_pow_dispatch_extension) <= ADDR(.m0_pow_refine_extension),
           "M0 pow hot path overlaps refinement")
    ASSERT(SIZEOF(.m0_pow_refine_extension) <= 0x18000,
           "M0 pow refinement overlaps comparison reference")
}
INSERT AFTER .flash_end;
