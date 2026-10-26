SECTIONS { . = 0x10000000; .text : { *(.text*) *(.rodata*) } .product 0x10010000 : { *(.product) } .parent_product 0x10020000 : { *(.parent_product) } /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
