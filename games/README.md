# MK61 game files

Copy these `.m61` files to the MK61S USB disk.

## File catalogue and provenance

The table records where every bundled game or image came from. When the exact
external publication is not present in the file or repository history, that is
stated explicitly instead of guessing an author or source.

| File | Contents | Provenance |
| --- | --- | --- |
| `Bumblebee Fly.m61` | Full MK-61 **Bumblebee Fly** game and its register setup | Extracted from the `mk61_games` and `mk61_game_setups` arrays inherited from the original [UN7FGO/MK61S_MINI](https://github.com/UN7FGO/MK61S_MINI) firmware when this fork moved its built-in games to `.m61` files. The upstream code did not record the original listing or author. |
| `Bumblebee.m61` | Small calculator-driven animation for the 16x2 display | Written specifically for this repository when M61 `print` and `trap` support was added. It is a new display-oriented example inspired by, but not copied from, the full `Bumblebee Fly.m61` bytecode. |
| `Chase HQ.m61` | 105-step MK-61 driving game with setup commands | Converted for this repository from Konstantin Sergeev's 1993 [Chase H.Q. listing](https://lordbss.narod.ru/pmk83.html). |
| `Fox Hunting.m61` | MK-61 logic game | Extracted from the embedded game library inherited from [UN7FGO/MK61S_MINI](https://github.com/UN7FGO/MK61S_MINI). The upstream code did not record the original listing or author. |
| `Infinity Story.m61` | MK-61 exploration game, called `Infinity store` in the old firmware menu | Extracted from the embedded game library inherited from [UN7FGO/MK61S_MINI](https://github.com/UN7FGO/MK61S_MINI). The upstream code did not record the original listing or author. |
| `Lunolet 1.m61` | **Lunolet-1** spacecraft manoeuvring and landing simulator | Extracted from the embedded game library inherited from [UN7FGO/MK61S_MINI](https://github.com/UN7FGO/MK61S_MINI). The game is the classic `Lunolet-1` from the Soviet calculator-program series; the exact transcription used by the upstream firmware was not attributed there. |
| `Mult Lunolet.m61` | MK-61 program imported under the supplied **Mult Lunolet** name | Supplied locally by the project maintainer. No author, publication, or upstream URL is embedded in the file or recorded in Git history. |
| `Naval Battle.m61` | MK-61 naval battle game | Extracted from the embedded game library inherited from [UN7FGO/MK61S_MINI](https://github.com/UN7FGO/MK61S_MINI). The upstream code did not record the original listing or author. |
| `Samurai.m61` | MK-61 game with its register setup | Added as an `.m61` file during the built-in-library-to-filesystem migration in this repository. No earlier in-tree copy, external listing, or author attribution is recorded. |
| `Wumpus.m61` | MK-61 **Wumpus** game with generated initial state | First added to this fork's embedded game library and then exported to `.m61`. The external listing or author used for that port was not recorded. |
| `br8kout.ch8` | **Br8kout** CHIP-8 ROM by SharpenedSpoon, 199 bytes | Downloaded unchanged from the [Chip8 Community Archive](https://github.com/JohnEarnest/chip8Archive), released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). |
| `fuse.ch8` | **Fuse** CHIP-8 ROM by John Earnest, 424 bytes | Downloaded unchanged from the [Chip8 Community Archive](https://github.com/JohnEarnest/chip8Archive), released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). |
| `space-invaders.ch8` | **Space Invaders v0.9** CHIP-8 ROM by David Winter, 1283 bytes | Taken unchanged from the [Zophar public-domain CHIP-8 Games Pack](https://www.zophar.net/pdroms/chip8/chip-8-games-pack.html). |
| `pacman-120x28.wbmp` | Original 120x28 monochrome Pac-Man scene for testing the WBMP viewer | Original artwork by the MK61S_MINI project author, drawn specifically for this project in collaboration with Codex. It was not copied from an external image. |

## Bumblebee display example

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

Their SHA-1 values are respectively
`0cd895dc3d489d0e40656218900a04310e95f560` and
`31fc1c53cc610a9f4b9c5705c5a0f33fc028d123`, while Space Invaders is
`f100197f0f2f05b4f3c8c31ab9c2c3930d3e9571`.

The SHA-1 value of `pacman-120x28.wbmp` is
`c11baa9b3207fa89657d4545a0d2b6643fea0256`.
