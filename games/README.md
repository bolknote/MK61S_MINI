# MK61 game files

Copy these `.m61` files to the MK61S USB disk.

`Bumblebee Fly Trap.m61` is the trap-driven variant of `Bumblebee Fly.m61`.
At program address 9 it reads the game's packed position from `RA` and moves a
display-safe `*` with ANSI cursor commands. The 9 x 7 field is folded, in row
order, into the four free 16-character rows of the 6-row screen; the normal
calculator indication remains in the first two rows. Only the old and new
marker cells are overwritten, and `print` does not clear the screen. The two
`RECE55` stops are changed to returns so the M61 trap remains active throughout
the flight. `RA=1e-2`...`9e-8` covers the original seven coordinate columns.
The original file is kept unchanged.
