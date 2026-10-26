mk61_m0_pow_dispatch = 0x101612f5;
__aeabi_ddiv = 0x100f7e89;
mk61_m0_sqrt = 0x1016bb01;
pow_rsqrt = 0x10160ef1;
factor_rsqrt_seeds = 0x101615c8;
mk61_m0_pow_rsqrt_boundary = 0x10160025;
mk61_m0_pow_square_exact = 0x10161e01;
mk61_m0_pow_dispatch_ordinary = 0x10162201;
PHDRS { entry PT_LOAD FLAGS(5); rsqrt PT_LOAD FLAGS(5); }
SECTIONS {
 .pow 0x101614cc : { *(.m0_pow_dispatch_extension) } :entry
 .rsqrt 0x10162800 : { *(.m0_pow_rsqrt_fast_only) } :rsqrt
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) }
}
