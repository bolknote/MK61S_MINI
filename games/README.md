# MK61 game files

Copy these `.m61` files to the MK61S USB disk.

`Bumblebee.m61` is a small calculator-driven animation for the 16x2 display.
Set the angle switch to `Г` and the bee `-0008` flies to the right; switch to
`Р` and `8000-` flies to the left. The middle `ГРД` position is not used.
Hitting either wall produces the calculator's `ЕГГОГ` error.

All movement, wall checks, angle-mode detection (`272`, `F cos`), and cursor
coordinates are calculated by the MK-61 bytecode. The M61 layer blanks and
owns the display, then two traps publish the right- and left-facing frames
every 300 ms. The current coordinate is encoded as the exponent of `10^R0`,
so `{X:e}` can be used directly as the ANSI column.
