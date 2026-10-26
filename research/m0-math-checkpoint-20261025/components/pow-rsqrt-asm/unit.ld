mk61_m0_pow_dispatch = 0x101612f5;
__aeabi_ddiv = 0x100f7e89;
mk61_m0_sqrt = 0x1016bb01;
pow_rsqrt = 0x10160ef1;
factor_rsqrt_seeds = 0x101615c8;
mk61_m0_pow_rsqrt_boundary = 0x10160025;
mk61_m0_pow_square_exact = 0x10161e01;
mk61_m0_pow_dispatch_ordinary = 0x10162201;
PHDRS { unit PT_LOAD FLAGS(5); }
SECTIONS { .quotient 0x10170000 : { *(.m0_pow_center_quotient_unit_only) } :unit
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
