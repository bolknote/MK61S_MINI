SECTIONS { . = 0x101d0000; .text : { *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) } }
