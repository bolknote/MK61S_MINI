# Compact tails and28-row batches

At270 MHz, candidate-only passes measured0.784029 and0.783943 s/token against
the archived0.8017425 reference:2.21% and2.22% less time. No control was rerun.
A026B051/442C52D5 is installed; the Spectrum BIOS/APP/AY/ROM are unchanged.

Weight scales follow the actual row count instead of the maximum tile count,
removing the destination gap that previously forced synchronous tail reads.
For this128-hidden/384-intermediate model, narrow matrices use28 rows and wide
matrices retain8. Full narrow tiles occupy2016 bytes, below the2048-byte DMA
limit. Even row counts retain16-byte scale alignment. Sparse tiles remain8.
Workspace grows by592 bytes over the24-row version; no PSRAM DMA buffer grew.

Worker jobs per pass fell from3666 to3279. All2996 eligible next-tile reads
used prefetch. Full row coverage, greedy tokens and all-row checksums match.
ASan/UBSan checks cover all arithmetic modes, full logits,64-position KV,
workspace guards, zero layout-gap refusals, sparse/refused DMA, cancellation,
faults, joins and thaw. Full PicoCalc UI/model tests and the ARM build passed.

Final state:125 MHz calculator, CLOSED/NONE, owned launcher removed and
CDC/MSC/lease closed. These are short-context2+2-token measurements.
