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
    /* Diagnostic-only arm/fire records use an otherwise empty Flash gap.
     * No math slot or ROMCACHE boundary is moved. */
    .audio_alarm_diagnostics 0x10148000 : {
        *(.audio_alarm_diagnostics)
        *(.audio_alarm_diagnostics.*)
        *(.audio_alarm_diagnostics_data)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_math_extension) + SIZEOF(.m0_math_extension) <= ADDR(.audio_alarm_diagnostics),
           "M0 math overlaps audio alarm diagnostics")
    ASSERT(ADDR(.audio_alarm_diagnostics) + SIZEOF(.audio_alarm_diagnostics) <= 0x1014d800,
           "Audio diagnostics exceed existing Flash gap")
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
    .m0_pow_exact_extension 0x1014e000 : {
        *(.m0_pow_exact_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.m0_pow_exact_extension) <= 0x2000,
           "Exact pow endpoint comparison exceeds its8KiB slot")
    ASSERT(ADDR(.m0_log_product_extension) + SIZEOF(.m0_log_product_extension) <= ADDR(.m0_pow_exact_extension),
           "Log product helpers overlap exact pow endpoint comparison")
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
    /* The shared product at cache offset0xc8 aliases argument code.
     * A table row at that offset then causes three-way contention.
     * Place a byte-identical private entry in the unused sin/cos span;
     * shared products and pow keep their original addresses and bytes. */
    .m0_trig_product_extension 0x10171c00 : {
        *(.m0_trig_product)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.m0_trig_core_extension) + SIZEOF(.m0_trig_core_extension) <= ADDR(.m0_trig_product_extension),
           "Sin/cos hot code overlaps its private bounded product")
    ASSERT(ADDR(.m0_trig_product_extension) + SIZEOF(.m0_trig_product_extension) <= ADDR(.m0_trig_core_extension) + 0x2000,
           "Sin/cos bounded product exceeds its8KiB cache index span")
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
    /* AI diagnostics and model startup are cold; reserve flash beyond the qualified math slots,
     * rather than growing the main image into their fixed load addresses. */
    .ai_diagnostic_extension 0x10180000 : {
        *(.ai_diagnostic_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.ai_diagnostic_extension) <= 0x10000,
           "AI diagnostic code exceeds its64KiB flash slot")
    /* Same 8KiB cache indices as the0.729s/token E0CDF5AB model code.
     * UI/diagnostic growth must not move these instruction streams. */
    .ai_inference_extension 0x101ac248 : {
        *mk61_ai_model.cpp.o(.text*)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.ai_inference_extension) <= 0x6000,
           "AI inference exceeds its24KiB flash slot")
    .ai_attention_extension 0x101b4000 : {
        *(.ai_kv_stream_extension)
        *(.ai_attention_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.ai_inference_extension) + SIZEOF(.ai_inference_extension) <= ADDR(.ai_attention_extension),
           "AI model overlaps attention code")
    ASSERT(SIZEOF(.ai_attention_extension) <= 0x1000,
           "AI attention exceeds its4KiB slot")
    .ai_fp32_extension 0x101b5000 : {
        *(.ai_fp32_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(SIZEOF(.ai_fp32_extension) <= 0x1000,
           "Exact FP32 helper exceeds its4KiB slot")
    ASSERT(__flash_binary_end <= 0x101c0000,
           "Firmware overlaps the persistent Spectrum ROM cache")
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
    /* Newly live AI-only float sqrt code/table: fixed free Flash space. */
    .ai_math_extension 0x101b5400 : {
        *(.ai_math_extension)
        __flash_binary_end = MAX(ABSOLUTE(__flash_binary_end), ABSOLUTE(.));
    } > FLASH
    ASSERT(ADDR(.ai_fp32_extension) + SIZEOF(.ai_fp32_extension) <= ADDR(.ai_math_extension),
           "AI FP32 helpers overlap AI math")
    ASSERT(ADDR(.ai_math_extension) + SIZEOF(.ai_math_extension) <= 0x101c0000,
           "AI math overlaps persistent ROMCACHE")
}
INSERT AFTER .flash_end;
