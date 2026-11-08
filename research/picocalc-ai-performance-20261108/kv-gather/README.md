# KV gather and parallel attention on PicoCalc

The measured combined firmware **D1752771 / AD0AD899** ran at270 MHz on both
RP2040 cores. Two short passes measured **0.7140895 and0.7142315 seconds/token**
against the requested0.717 target: a0.39–0.41% reduction, not a substantial
speedup. Each pass has2 prefill and2 decode tokens, the full classifier, INT8
activations and Q4 weights. The model SHA is in `device-receipt.json`.

All generated tokens and linear checksums match the archived reference.
There were no I2C errors or LCD freeze violations; clocks returned to125 MHz.
The four existing improvements remain: fast ordinary chat, the64/128/256
context diagnostic, activation reuse in Q/K/V and gate/up, and shared KV
reads for paired query heads. No weights, tokenizer or context limits changed.
This short result does not establish performance at long context.

## Implementation

`KVStream` borrows at most2048 bytes from the activation lookup allocation,
which is dead during attention. It gathers up to16 positions of one KV head
into one bounded scatter DMA read. Each transfer finishes before its data is
used; the next linear operation rebuilds the activation table. No extra KV
or workspace allocation is required. A refused transfer falls back to direct
reads; failed completion returns an I/O error without leaving DMA pending.

Independent query heads can run on both cores, reading the same gathered
chunk and writing disjoint output ranges. Reductions within each head retain
the original position/dimension order. Cancellation is checked between chunks,
and workers are joined before the shared buffer is overwritten. Gather and
attention helpers occupy a bounded flash section at0x101b4000; the existing
model section retains its pinned address. A linker guard prevents firmware
from reaching the Spectrum ROM cache at0x101c0000.

## Evidence and limits

`device-performance.json` is the unmodified diagnostic result;
`device-receipt.json` records identity, model hash, timing comparison and clean
release. `device-firmware-manifest.json` and `measured-source-pins.json` identify
the tested combined build. Its JSON does not expose KV transaction counters,
so transaction reduction is verified by HOST tests, not claimed as measured
on the board. The combined build includes parallel attention and unrelated
Spectrum/clock/UI changes; this is not an isolated KV-gather ablation.

HOST checks cover full-logit/KV equivalence, bounded transfers, transaction
and byte counts, synchronous/refused DMA, partial-read failure, cancellation,
worker joins and buffer guards under ASan/UBSan. The source commit includes
only the AI core, native cache binding, linker section and relevant test;
other agents retain their Spectrum, clock and cold-chat changes. Consequently
the recorded firmware identity describes the tested combined image, not a
claim that this partial source commit reproduces that binary by itself.

The earlier E98DCB5B and EB8C4DDD prepared candidates were never flashed.
The final measurement reused the coordinator-installed D1752771, did not
modify STM32 or ROMCACHE, removed its own benchmark APP, and released CDC and
the board lease in CALCULATOR/CLOSED/NONE state.
