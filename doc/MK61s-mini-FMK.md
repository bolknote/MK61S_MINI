# FMK1 bitmap font format

Files use the `.fmk` extension and appear as type `f1` in the calculator's
file explorer. Running a font on UC1609 applies it to the text renderer until
restart; View uses it temporarily. LCD1602 A00/A02 can only preview a font by
scaling eight glyphs into all eight HD44780 CGRAM slots.

FMK1 describes both monospaced and proportional fonts. Firmware version 1
parses both variants but displays and applies monospaced fonts only.

## Header

All multibyte integers are little-endian.

| Offset | Size | Meaning |
| ---: | ---: | --- |
| 0 | 4 | ASCII magic `FMK1` |
| 4 | 1 | Flags: bit 0 is `monospaced`; other bits are zero |
| 5 | 1 | Cell width or maximum glyph width, 1..16 |
| 6 | 1 | Glyph height, 1..32 |
| 7 | 1 | Bits 7..4: default advance minus one; bits 3..0: line gap |
| 8 | 2 | Glyph count |
| 10 | 1 | Codepoint range count |
| 11 | 1 | Reserved, zero |
| 12 | 2 | Complete file size, maximum 1536 bytes |
| 14 | 2 | CRC-16/CCITT-FALSE; these two bytes are treated as zero |

The header is followed by codepoint ranges. Each three-byte range stores a
16-bit first codepoint and an 8-bit glyph count minus one. Ranges are sorted,
must not overlap, and implicitly assign consecutive glyph indices.

## Glyph bitstream

The first glyph starts immediately after the range directory. Bits are written
most-significant first and records have no byte alignment.

Proportional records begin with `width - 1` and `advance - 1`, four bits each.
Monospaced records omit these fields.

Every record then has one mode bit:

* `0`: exactly `width * height` raw pixels follow.
* `1`: bit-RLE tokens follow until `width * height` pixels are produced.

An RLE token begins with one bit:

* `0`: four bits store `literal length - 1`, followed by 1..16 pixels.
* `1`: five bits store `run length - 2`, followed by the repeated pixel;
  the token represents 2..33 pixels.

This makes raw data cost one bit per pixel plus one mode bit. The converter
uses dynamic programming to find the shortest RLE tokenization independently
for each glyph, then stores raw data whenever RLE would not be smaller.

## Converting TTF/OTF

The native converter uses FreeType and therefore accepts every scalable or
bitmap font format enabled in the local FreeType build. This normally includes
TTF, OTF/CFF, TTC, Type 1, CID, BDF, PCF, PFR and Windows FNT.

```bash
tools/build_fmk_font.sh font.otf font.fmk --cell 5x8 --chars ascii,cyrillic
tools/build_fmk_font.sh font.bdf font-3x5.fmk --cell 3x5 --size 20
```

The bitmap uses a shared baseline box for all glyphs before downscaling, so
vertical alignment remains consistent. `--compression auto` is the default.
The default line gap is 1 pixel through height 5, 2 pixels through height 8,
and zero above that; it can be overridden with `--line-gap`.
