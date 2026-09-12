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

`family=0` means the fixed 5x8 monospaced UI (shown as `5x8`), and `1` is the
native Ark Pixel proportional UI. Legacy wire value `2` remains an alias for
Ark Pixel so an already-built APP cannot lose font service after an update; it
is no longer offered by the settings screen. `family=3` is the active external
FMK UI face selected from a direct child `Fonts/*.FMK`; the C5 filename is its
user-visible name. Legacy root files `UI12.FMK`, `UI14.FMK` and `UI16.FMK`
remain a migration fallback for an old saved selection but are not the catalog.
Family 0 ignores the stored 12/14/16 size. On every UC1609 configuration,
including F401, calculator digits use a separate fixed twelve-position
renderer and never consume this font service. Proportional UI fonts themselves
remain F411-only.
Size is the stable UI selection, not a request to scale outlines. It chooses
native Ark strikes 10/12/16 px whose complete Russian line envelopes are
12/14/17 px. For family 3 it reports the selected file's intrinsic 12/14/16
height; each size is a separate catalog face and is never scaled. INFO supplies
ascent, descent, interline gap and real `height`
in its formerly reserved last byte. A zero `height` from an older resident
means `size`. The gap is one pixel for size 12 and two for 14/16. On unsupported
hosts, when family 3 is not currently resident, or when any service/metadata
check fails, retain the monospaced path.

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
characters become `?`; Ark's missing ≤/≥ deliberately use `<`/`>` and set
`fallback=1`. An FMK record is row-padded by the resident decoder and reports
`bearing_x=0`, `bearing_y=height`; its per-glyph `advance` is preserved. A valid
UI package contains both space and `?`, has a maximum 16x16 cell and a line gap
of at most four pixels.

## Markdown client

The F411 built-in viewer and a portable `MARKDOWN.APP` built with the optional
client use one shared source adapter.
Each layout pass snapshots the current font preference. Both measurement and
drawing use the same advances; bold adds one column and italic reserves the
maximum actual row shear, preventing adjacent letters from colliding.
Code blocks retain the existing monospaced font; inline code stays 5x8 and is
baseline-aligned without synthetic slant/bold stretching. The small OLED and
character-only paths keep their previous layout.

The guaranteed Pixel tables remain solely in resident Flash; an external FMK
lives in the already allocated F411 BULK arena. The APP contains the bridge
and text layout, not duplicate font tables or a heap glyph cache. The bounded
glyph record is temporary stack storage. USB storage temporarily revokes the
FMK arena; after unmount the resident resolves the file by its persisted,
case-insensitive filename key, reloads and revalidates it before the service
exposes family 3 again. A missing, renamed, colliding or invalid selection
fails closed to the resident Pixel face.

Checks:

- `tests/run_markdown_ui_font_tests.sh`: native/portable bridge equivalence,
  every glyph and emphasis combination, snapshot stability, old-host fallback,
  invalid records and bounds; optional `MK61_TEST_SANITIZERS=1`.
- `tests/run_portable_system_arm_tests.py`: real ARM resident raster calls,
  exact final Markdown framebuffers for every built-in size and the legacy
  family alias, Cyrillic, symbol fallback, and unchanged monospaced code
  blocks/inline code.

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
new presentation feature nor Ark Pixel notices. F401 keeps the original
monospaced layout and the original 12 KiB packed Markdown ceiling.

Measured with pinned ARM GCC 14.2.1, the disabled build is 12172 bytes packed
and 15312 bytes unpacked for `MARKDOWN.APP`, with 12 bytes of BSS. `SETUP.APP`
is 6782 bytes packed and 9284 bytes unpacked, also with 12 bytes of BSS. The
enabled portable variants are retained for F411 and cross-resident development.
A third-party board-neutral system APP may use the default client and will
safely fall back on an older host, or explicitly request the same compact build
with `--no-ui-fonts`.

The complete Ark Pixel notice is shipped in `UI_FONT_LICENSES.zip` beside
the standalone F411 binaries that actually contain the raster tables.
