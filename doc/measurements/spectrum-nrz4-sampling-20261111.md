# NRZ4: intact data, invalid stop symbol

2026-11-12. BC3E68F9 / AE970EF0 is installed with a full verified readback.
Its first hardware AYABC test failed with another invalid stop symbol. All
previous failed hardware runs remain failed; strict qualification has not passed.

An SD-only observer on the installed E9EB41B5 image captured the first published
native error before Context destruction. It copied 744 bytes with no native or
MMIO writes, then printed the copy. The first error in that diagnostic was -45:
the stop word for four-byte frame6 was 0x3 instead of 0xF. The GPIOB lanes were
high and the GPIOC lanes low. The received header's sequence93, count244, job31
and success status were consistent.

The decoder had already converted the first six payload words in place. Joining
those first24 decoded bytes to the61 untouched MSB-first input words recovered
the entire268-byte frame. Its received and calculated CRC were both EF7C4BF7.
Replaying this reconstructed input and stop3 through the actual reference ARM
decoder produced the exact captured536-byte partial decode buffer. The payload
was intact in this capture. The earlier -46 failure is still preserved; a timing
model demonstrates how a delayed data edge can instead leave all stops valid
while corrupting the payload, without proving that earlier failure's cause.

The candidate retains the finite eight-instruction receiver and2Msymbol/s wire
rate, but uses a64MHz PIO state machine instead of16MHz. At the stock125MHz system
clock its exact divider is1+244/256. WAIT delay23, SET delay31 and JMP delay30
sample each nibble375ns into its500ns symbol,125ns later. The shorter PIO cycles
leave room for PUSH/JMP/WAIT before the next start. Simply extending the old
16MHz delay failed the model by accumulating start-detection phase error and was
not installed or written into PIO memory.

WAIT's delay starts after the condition is met; JMP delay applies on both branch
outcomes. These semantics follow sections3.4.2–3.4.3 of the official
[RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf).
The model includes fractional-divider quantization, phase offsets, ±1% clock
error and a single delayed GPIOC data/stop edge up to312.5ns:4,608 cases passed
for the candidate;772 cases failed for the old receiver. This is a modeled range,
not a measured hardware worst-case bound. FIFO drain is idealized in that model.

A separate scheduling fix consumes a completed RESULT before deciding admission
for the next job. The old service returned to the I/O worker without starting
the next prepared block, leaving a window for a keyboard I2C transfer. Actual
reference/candidate ARM execution verifies one result publication and immediate
next-job admission, while preserving real errors and an already completed final
WRITE acknowledgement when I2C is busy. Priming improvements remain to be measured.

The combined current source build was stable before/after compilation and was
sealed into read-only source copies. All5 ordinary game probes rebuilt byte-for-
byte identically. Actual candidate ARM NRZ, scheduling and keyboard regressions,
the M3 audio suite and the full platform ASan/UBSan suite passed. Static SRAM
remains120,484 bytes and heap108,892 bytes. M3 B89B1FE5 remains unchanged at72MHz;
Pico CPU remains125MHz. The source snapshot includes the reviewed AI/LCD changes
from the parallel owner and lets later workspace edits proceed independently.

The prepared hardware sequence is one Pico installation/readback and planned
normal reboot, then four600-frame AY/YM×ABC/ACB tests. The30,000-frame long test is
blocked until all four same-package short tests pass. Criteria are unchanged;
there is no retry, automatic rollback, settings/ROM/game rewrite or M3 update.

The actual first AYABC short run stopped after8 delivered blocks and2 measured
game frames: M3_ERROR=-45, NRZ errors1, prime20,461us, maximum successful block
3,807us. The later PIO sampling did not eliminate the physical fault. Battery,
keyboard and I2C counters stayed clean. The remaining three short runs and long
were not started. Owned SD files were removed and APP/M3/CDC/lease released.
The20ms maximum hold includes deliberate bounded fault recovery; it is not a
measured late synthesis response. A new read-only observer must target this
exact installed ELF before the next targeted diagnostic window.
