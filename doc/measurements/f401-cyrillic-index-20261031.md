# F401 Cyrillic glyph index, 2026-10-31

F401 indexes the consecutive U+0410..U+044F glyphs arithmetically, retaining a sorted table for the other 22 non-ASCII codepoints. The generator checks that the complete consecutive alphabet remains in the reviewed repertoire. Glyph order, bitmap bytes, metric dictionaries, records and the public Glyph ABI are unchanged. F411 and actual Pico preprocessing retain their previous token stream, including when the HOST-only test selector is supplied to an ARM build.

With the preceding DCW candidate, Classic V3 native BIN changes from 258792 to 258696 bytes, saving 96 bytes. It has 3448 bytes free and remains 648 bytes short of the original 4096-byte reserve. These measurements include the separate DCW work in progress; this Cyrillic commit does not include it, and neither change is qualified as a release. The combined RAM check passes at 29844/52428 bytes and the maximum per-function frame is 1304/2048.

Both table formats pass ASAN/UBSAN. Every supported BMP codepoint is compared against the original atlases: 543 glyphs and 24845 pixels per format, with exact metrics. Explicit checks cover U+0401, U+0410, U+044F and U+0451, adjacent missing codepoints, and outside-BMP fallbacks. The generated file reproduces with `generate_ui_fonts.py --check`. Independent Root review additionally compared all Unicode codepoints and uint32 probes against the legacy lookup without discrepancies. No hardware was accessed.

The adjacent JSON contains exact source pins and before/after measurements. The frozen research packet is retained under `.build/f401-runner-size-20261031-001/font-cyrillic-review-001`.
