PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { . = 0x20038ee4; .product : { KEEP(*(.scratch_y.m0_exp_product_only)) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }
