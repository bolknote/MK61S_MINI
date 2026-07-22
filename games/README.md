# MK61 game files

Copy these `.m61` files to the MK61S USB disk.

`Bumblebee Fly Trap.m61` keeps the calculator program as the animation and
calculation engine. The original `ПП 95` subroutine copies a frame through the
stack with six `В↑` instructions: the first three replace transient stack
values and the next three hold the clean frame. A trap before the fourth `В↑`
(address 98) publishes that stable calculator indicator through one
`print "{X2}"`; ordinary intermediate indicator refreshes stay hidden while the
M61 script owns the display. The print targets only the normal indicator row
and does not clear the screen. The two `RECE55` stops are changed to returns so
the trap remains active during the flight. Before the main run, `kbd 09`
selects the original game's required `ГРД` (grade) switch position.

The branch and call operands in both Bumblebee files use the BCD program-address
bytes entered on an MK-61 (`95`, `22`, and so on), rather than hexadecimal
encodings of decimal addresses (`5F`, `16`, ...).
