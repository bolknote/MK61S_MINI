EXTERN(mk61_m0_bound80_square mk61_m0_bound80_multiply mk61_m0_bound80_compare mk61_m0_bound80_wide32)
PHDRS { text PT_LOAD FLAGS(5); }
SECTIONS { .unit 0x101e0000 : {
  KEEP(*(.m0_pow_bound80_square)) KEEP(*(.m0_pow_bound80_wide32))
  KEEP(*(.m0_pow_bound80_multiply)) KEEP(*(.m0_pow_bound80_compare))
} :text
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) }
}
