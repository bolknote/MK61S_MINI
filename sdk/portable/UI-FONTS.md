# Optional proportional UI glyph service

UC1609 resident firmware with the optional proportional UI implementation
advertises `MK61_SERVICE_CAP_UI_FONT` in the unchanged common service table.
The added operation is `MK61_SERVICE_UI_FONT` (27); existing operation numbers,
ABI version and the common table's binary layout are unchanged.

Clients **first check the capability**, then call:

```c
mk61_service_ui_font_info info = {0};
services->call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_INFO, 0,
               sizeof(info), &info);
```

`family=0` means the legacy UI is selected, `1` is DejaVu Sans and `2` is Roboto.
Size is the full 12- or 14-pixel glyph envelope, not FreeType ppem. The record
also supplies ascent, descent and a two-pixel interline gap. On unsupported
hosts, or when any service/metadata check fails, retain the monospaced path.

For a glyph, initialize `mk61_service_ui_glyph.family` and `.size` from this
snapshot, then call `GLYPH` with the Unicode code point in `b`, the exact
40-byte record size in `c`, and its address in `payload`. The resident copies
at most 32 raster bytes; no Flash pointers cross into the APP. Both metadata
and raster requests reject null pointers, mismatched record sizes and invalid
font choices. All records are fixed C layouts with explicit-width fields.

The 1-bit bitmap is row-major, MSB-first, with `ceil(width/8)` bytes per row,
matching the existing FMK/builtin raster. Draw at
`(pen_x+bearing_x, baseline_y-bearing_y)` and advance by `advance`.
Validate returned dimensions/metrics before indexing any bitmap. Unknown
characters become `?`; missing Roboto arrows use same-size DejaVu and set
`fallback=1`. At least one column remains between unstyled glyph ink boxes.

## Markdown client

The built-in viewer and portable `MARKDOWN.APP` use one shared source adapter.
Each layout pass snapshots the current font preference. Both measurement and
drawing use the same advances; bold adds one column and italic reserves the
maximum actual row shear, preventing adjacent letters from colliding.
Code blocks retain the existing monospaced font; inline code stays 5x8 and is
baseline-aligned without synthetic slant/bold stretching. The small OLED and
character-only paths keep their previous layout.

Font tables remain solely in resident Flash. The APP contains the bridge and
text layout, not duplicate font tables or a heap glyph cache. The bounded
glyph record is temporary stack storage.

Checks:

- `tests/run_markdown_ui_font_tests.sh`: native/portable bridge equivalence,
  every glyph and emphasis combination, snapshot stability, old-host fallback,
  invalid records and bounds; optional `MK61_TEST_SANITIZERS=1`.
- `tests/run_portable_system_arm_tests.py`: real ARM resident raster calls,
  exact final Markdown framebuffers for four font choices, Cyrillic, arrow
  fallback, and unchanged monospaced code blocks/inline code.

The full ARM suite requires unstripped **test-only** residents built with
`MK61_MATH_BACKEND=0` (LIBM). Its mocked environment does not initialize the
calculator core or emulate STM32 bit-band accesses; using a product CORE
resident would fail a preceding BASIC math test before reaching font checks.
The runner rejects that mismatch explicitly. Product configuration is
unchanged: real CORE math and context preservation are checked separately by
`tests/run_mk_math_tests.sh`, with Flash and evictable-SRAM tables.

For exact shipping CORE residents, use `--ui-only` to qualify the UI without
the transcendental probe. This replaces only BASIC's transcendental expression
with ordinary arithmetic; language state exchange, editor/monospace roles,
settings, ABI/bounds, and exact Markdown raster checks still run. The output
explicitly labels this as UI qualification, not a full math-suite pass. This
mode avoids inflating production F401 Flash limits just to fit a LIBM fixture.

These are software checks, not a substitute for physical readability testing.

## Explicit F401 UC1609 APP budget

The UC1609 `f401-product-classic-v3` packed Markdown allowance becomes **13 KiB
(13312 bytes)** for this new feature. This changes only the external-storage
APP container ceiling, not the resident Flash/RAM, stack-frame or loader
allocation limits. The character-display 4096-byte Markdown budgets are
unchanged.

Measured with the pinned ARM GCC 14.2.1 toolchain:

| Artifact | Before | With shared font renderer | Difference |
|---|---:|---:|---:|
| Packed `MARKDOWN.APP` | 12169 | 12669 | +500 bytes |
| Unpacked image | 15312 | 16016 | +704 bytes |
| APP BSS | 12 | 12 | 0 |
| APP image + BSS | 15324 | 16028 | +704 bytes |

The first implementation duplicated the glyph draw loop (12872-byte APP).
It was reduced to one canonical row-padded raster renderer, keeping bounds
checks and style-aware wrapping, rather than deleting functionality to fit
the old ceiling's 119-byte headroom. The new ceiling has 643 bytes spare.

The measured F401 linker interval was `0x20007048..0x2000E700`: after aligning
the pool start to 32 bytes, 30368 bytes are available before heap/temporary
allocations. This APP reserves `align32(16028)=16032` bytes, leaving 14336
bytes for other dynamic allocations (12288 after a separate 2048-byte input
buffer). This is not a promise that all of those bytes remain free at runtime:
the existing shared-memory allocator rejects a load that would overlap a live
buffer or heap. The 6 KiB stack reserve plus 256-byte guard above the pool is
unchanged. Standalone APP stack analysis passed (maximum recorded frame 752
bytes). Final matrix reports remain authoritative for each exact resident.

Release packaging includes the complete DejaVu/Roboto notices inside F401
bundles and as `UI_FONT_LICENSES.zip` beside standalone F411 BIN files.
