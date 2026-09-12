# Reviewed UC1609 UI rasters

These three proportional faces are exact native bitmap strikes from Ark Pixel
Font 2026.09.01. They replace tiny monochrome renders of outline fonts: no
outline hinting, antialiasing or resampling is involved.

The settings value remains the UI size expected by existing firmware and APPs.
The native design size and complete Russian line envelope are:

| UI setting | Native Ark strike | Ascent | Descent | Envelope | Gap | Rows |
|---|---:|---:|---:|---:|---:|---:|
| 12 | 10 px | 10 | 2 | 12 | 1 | 5 |
| 14 | 12 px | 12 | 2 | 14 | 2 | 4 |
| 16 | 16 px | 14 | 3 | 17 | 2 | 3 |

The 17-pixel envelope at the largest setting is intentional: it preserves both
`Й` and Russian/Latin descenders without clipping and still fits three rows in
64 pixels. The optional UI-font service reports this real envelope in the byte
formerly reserved in its six-byte INFO record; new clients accept zero there
from older residents and then use the legacy `size` value.

The repertoire is ASCII, Russian including Ё/ё, degree, four arrows, ellipsis
and ≤/≥. Ark contains every glyph except ≤/≥; firmware deliberately aliases
those two to the corresponding ASCII comparison signs and marks the result as
a fallback. Unknown characters still become `?`.

## Reproduction

Normal firmware builds consume `code/ui_font_data.inc`; FreeType and the BDF
sources are host-only inputs. Build `font_preview.cpp` as described in the
adjacent `README-preview.md`, then export the `latin` BDF files:

```sh
font_preview ark-pixel-10px-proportional-latin.bdf pixel-12.json --height 12
font_preview ark-pixel-12px-proportional-latin.bdf pixel-14.json --height 14
font_preview ark-pixel-16px-proportional-latin.bdf pixel-16.json --height 17
python3 tools/generate_ui_fonts.py
python3 tools/generate_ui_fonts.py --check
bash tests/run_ui_font_tests.sh
```

The exporter selects the fixed bitmap strike, crops only all-zero BDF padding,
and preserves the source pixels, baseline and advances. The generated advance
also guarantees at least one blank column between adjacent ink boxes. JSON
checksums are pinned by the generator, so a source or FreeType change cannot
silently alter shipping glyphs.

## Source and licensing

- Ark Pixel Font release 2026.09.01:
  <https://github.com/TakWolf/ark-pixel-font/releases/tag/2026.09.01>
- Native proportional BDF SHA-256:
  - 10 px: `b1603ca3d30ba96612bc23ffbf61ea62dedb0c5e82eb42bdb45e36f29910b10c`
  - 12 px: `1a7d1a9c4ed6e4e0c5838258ced2294927a6ce1731707c1ae8cbd8ffe464a323`
  - 16 px: `a0132553941b3881aafa73f1391f8f8fce9e86f7d84bd819cdc7de6d87725e67`

Copyright (c) 2021, TakWolf. Ark Pixel Font is licensed under SIL Open Font
License 1.1; the complete notice is retained in `LICENSE-Ark-Pixel.txt` and is
packaged beside firmware containing the converted subset.

Only F411/UC1609 firmware compiles these tables. A00/A02, WS0010 and all F401
builds contain no proportional UI tables and allocate no RAM for them.
