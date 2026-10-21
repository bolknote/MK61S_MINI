/* Keep additional M0 math out of the previously timed .text/.rodata layout.
 * This address also stays beyond the synthetic load ranges objcopy derives
 * from the SDK's NOLOAD RAM sections when sealing the firmware footer.
 * Both code and tables execute/read directly from flash, with no RAM copy.
 */
SECTIONS {
    .m0_math_extension 0x10140000 : {
        *(.m0_math_extension)
        *(.m0_math_extension_data)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    /* Keep these leaf product helpers disjoint from the fixed log10
     * hot path in cache index space. Grouping the unchanged bodies also
     * decouples their placement from future platform text growth. */
    .m0_log_product_extension 0x1014d800 : {
        *(.m0_log_product_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_math_extension) + SIZEOF(.m0_math_extension) <= ADDR(.m0_log_product_extension),
           "M0 tables overlap relocated log product helpers")
    ASSERT(SIZEOF(.m0_log_product_extension) <= 0x200,
           "M0 log product helper group exceeds512bytes")
    .m0_asin_extension 0x10150d00 : {
        *(.m0_asin_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    .m0_asin_refine_extension 0x10156000 : {
        *(.m0_asin_refine_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
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
