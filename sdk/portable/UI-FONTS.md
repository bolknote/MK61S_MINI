# Optional proportional UI glyph service

UC1609 resident firmware with the optional proportional UI implementation
advertises `MK61_SERVICE_CAP_UI_FONT` in the unchanged common service table.
The added operation is `MK61_SERVICE_UI_FONT` (27); existing operation numbers,
ABI version and the common table's binary layout are unchanged.

The resident service is compiled only for F411/UC1609. Clients **first check
the capability**, then call:

```c
mk61_service_ui_font_info info = {0};
services->call(MK61_SERVICE_UI_FONT, MK61_UI_FONT_INFO, 0,
               sizeof(info), &info);
```

`family=0` means the fixed 5x8 monospaced UI (shown as `Mono`), `1` is DejaVu
Sans and `2` is Roboto. Family 0 ignores the stored 12/14 size. On F411/UC1609
calculator digits use a separate fixed twelve-position renderer and never
consume this font service; F401 keeps its compact calculator renderer.
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

The F411 built-in viewer and a portable `MARKDOWN.APP` built with the optional
client use one shared source adapter.
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

## F401 exclusion contract

Official F401 bundles invoke `build_portable_app.py --no-ui-fonts`. This
removes the service bridge, proportional measurement/drawing branches and live
font chooser from `MARKDOWN.APP` and `SETUP.APP`; it is not merely a run-time
fallback. The resident, APP files and bundle therefore contain neither the
new presentation feature nor DejaVu/Roboto notices. F401 keeps the original
monospaced layout and the original 12 KiB packed Markdown ceiling.

Measured with pinned ARM GCC 14.2.1, the disabled build is 12172 bytes packed
and 15312 bytes unpacked for `MARKDOWN.APP`, with 12 bytes of BSS. `SETUP.APP`
is 6782 bytes packed and 9284 bytes unpacked, also with 12 bytes of BSS. The
enabled portable variants are retained for F411 and cross-resident development.
A third-party board-neutral system APP may use the default client and will
safely fall back on an older host, or explicitly request the same compact build
with `--no-ui-fonts`.

Complete DejaVu/Roboto notices are shipped in `UI_FONT_LICENSES.zip` beside
the standalone F411 binaries that actually contain the raster tables.
