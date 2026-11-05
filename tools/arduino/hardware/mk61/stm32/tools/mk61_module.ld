/* System APP is linked directly for the resident SRAM overlay. */
ENTRY(mk61_module_entry)

MEMORY
{
  MODULE (rwx) : ORIGIN = MK61_MODULE_ORIGIN, LENGTH = 20K
}

SECTIONS
{
  .module_image ORIGIN(MODULE) : ALIGN(8)
  {
    __module_image_start = .;
    KEEP(*(.mk61_module_entry))
    *(.text .text.*)
    *(.rodata .rodata.*)
    *(.glue_7 .glue_7t)
    *(.vfp11_veneer)
    *(.v4_bx)
    *(.ARM.extab* .gnu.linkonce.armextab.*)
    __exidx_start = .;
    *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    __exidx_end = .;
    *(.data .data.*)
    __module_initializers_start = .;
    KEEP(*(.preinit_array .preinit_array.*))
    KEEP(*(.init_array .init_array.*))
    KEEP(*(.fini_array .fini_array.*))
    KEEP(*(.ctors .ctors.* .dtors .dtors.*))
    __module_initializers_end = .;
    __module_image_end = .;
  } > MODULE

  .module_bss (NOLOAD) : ALIGN(8)
  {
    __module_bss_start = .;
    *(.bss .bss.*)
    *(COMMON)
    __module_bss_end = .;
    __module_memory_end = .;
  } > MODULE

  /DISCARD/ :
  {
    *(.comment)
    *(.note*)
    *(.ARM.attributes)
  }
}

ASSERT(__module_memory_end <= ORIGIN(MODULE) + LENGTH(MODULE),
       "MK61 module does not fit the SRAM overlay")
ASSERT(__module_initializers_start == __module_initializers_end,
       "MK61 module has unsupported global constructors/destructors")
