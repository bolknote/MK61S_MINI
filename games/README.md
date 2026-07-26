# MK61 game files

Copy these `.m61` files to the MK61S USB disk.

`Bumblebee.m61` is a small calculator-driven animation for the 16x2 display.
The script selects `Г` on startup, and the bee `-0008` flies to the right;
switch to `Р` and `8000-` flies to the left. The middle `ГРД` position is not
used.
Hitting either wall produces the calculator's `ЕГГОГ` error.

All movement, wall checks, angle-mode detection (`272`, `F cos`), and cursor
coordinates are calculated by the MK-61 bytecode. The M61 layer blanks and
owns the display, then two traps publish the right- and left-facing frames
every 300 ms. The current coordinate is encoded as the exponent of `10^R0`,
so `{X:e}` can be used directly as the ANSI column.

`Bumblebee Fly.m61` is the earlier full MK-61 program port. It is kept as a
separate game and is not replaced by `Bumblebee.m61`.

## CHIP-8 ROMs

The CHIP-8 console opens unmodified `.ch8` ROMs from any C5 directory. Copy a
base CHIP-8 ROM of up to 3584 bytes to the `MK61S C5` disk and open it in
Explorer.

The console uses C5 type magic `C1`; those bytes are not added to the ROM.
Screen compatibility, the full 0-F key map and game aliases are documented in
[`MK61s-mini-CHIP8.md`](../doc/src/MK61s-mini-CHIP8.md).

Three ready-to-run examples are included:

- `fuse.ch8` — **Fuse** by John Earnest, 424 bytes. Use CHIP-8 keys
  `5/7/8/9` to move and `6` to place a piece.
- `br8kout.ch8` — **Br8kout** by SharpenedSpoon, 199 bytes. Use CHIP-8 keys
  `7` and `9` to move the paddle.
- `space-invaders.ch8` — **Space Invaders v0.9** by David Winter, 1283 bytes.
  Use `4/6` (or `Left/Right`) to move and `5` (or `OK`) to start and fire.

Fuse and Br8kout come from the
[Chip8 Community Archive](https://github.com/JohnEarnest/chip8Archive), whose
contents are released under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Space Invaders
comes from the
[Zophar public-domain CHIP-8 Games Pack](https://www.zophar.net/pdroms/chip8/chip-8-games-pack.html).
Their SHA-1 values are respectively
`0cd895dc3d489d0e40656218900a04310e95f560` and
`31fc1c53cc610a9f4b9c5705c5a0f33fc028d123`, while Space Invaders is
`f100197f0f2f05b4f3c8c31ab9c2c3930d3e9571`.
