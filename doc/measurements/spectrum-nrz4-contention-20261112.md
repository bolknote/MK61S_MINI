# Completed I2C replies must not hold idle audio pins

2026-11-12. Candidate509B5A22 / A8F361F8 is HOST-tested, not installed.
The physical tests remain unqualified. Pico125MHz, M372MHz and the2Msymbol/s
link are unchanged; the M3 image remains B89B1FE5.

The second targeted observer captured engine error-29 (16 consecutive missing
samples), with NRZ error0 and an active receiver. This run completed161 NRZ
blocks with zero framing errors. Its retained buffer belongs to the previous
successfully decoded frame, not a newly damaged stop/CRC frame. The original
controller's general `NRZ_VALIDATION_FAULT_CAPTURED` HOLD label and all raw bytes
are preserved; they must not be interpreted as a framing diagnosis here.

At failure the audio engine had published160 blocks/18,880 samples and counted
38 underruns. Maximum GPIO lease wait was12,752us, prime21,710us and maximum
successful block4,598us. All37 measured game frames stayed within1ms of their
deadline (maximum lag530us). Battery, keyboard and I2C errors were zero. Owned
SD files and all APP/M3/CDC/lease resources were released. The earlier short003
stop-symbol failure remains unresolved; this different run does not erase it.

The shared I2C state previously allowed a GPIO loan only from IDLE. DONE means
the physical transfer has already stopped and its reply is stored in SRAM, but
gameplay can keep core0 busy before it consumes that reply. Thus the audio
producer could unnecessarily wait on the game core after the bus was idle.

PINS_DONE now lets audio borrow those physically idle pins while preserving the
completed reply. Copying the reply before returning the pins leaves PINS;
returning the pins first leaves DONE. Atomic transitions support both orders
and prevent a new I2C request from overwriting a reply being copied. QUEUED,
WORKING, FILLING and active GPIO reservations remain exclusive. This fixes a
specific delay mechanism; hardware testing must determine its contribution to
the observed underruns.

The regression suite retains one reply through128 audio loans, exercises both
completion orders and checks10,000 concurrent replies with exact payloads.
Actual production ARM tests cover the copy paths, admission, immediate next
audio job with a pending reply, bounded fault recovery and cleanup. The platform
ASan/UBSan and M3 audio suites passed. Context remains5,120 bytes; only32 static
bytes were added, leaving108,860 bytes of heap.

A first-fault diagnostic records PIO FIFO stall flags/levels, remaining DMA
words, GPIO levels and receiver PC/SM. Each arm clears sticky flags for its own
SM only. Snapshots survive subsequent faults and timer wrap. This will distinguish
receiver stalls from an invalid symbol without relaxing stop/CRC checks,
timeouts, priming limits or the four-short-PASS prerequisite for a long run.

The next unified HOST candidate is1BDB4385 /161FEF7E. It combines these exact
seven Spectrum production files with four reviewed AI production replacements
(plus two AI tests) in an isolated copy of the sealed509 sources. The combined
source digest is f6b6607f4ddb239b25cb0e0131220cb61b9eab14ab60aa8175aeffe0f2a8fa51;
actual combined ARM NRZ/service/keyboard/AI tests passed against ELF
8abddafabe3734c70df962b6184fe6deb23c0791e405a0fc90884d6b097e502f.
Static SRAM and heap are unchanged. Package014 contains the unified Pico-only
installer and strict Spectrum controller with new one-shot phase identifiers;
standalone509 approval or old phase grants cannot authorize it. The unified
image remains uninstalled pending its own direct user GO and device window.

The user's subsequent clean-start instruction is implemented in package015:
one standard `crash clear` before DFU, no old payload read/save/compare, no old
Flash backup or state restoration. Only the newly written image is read back.
The new boot and all test endpoints require CRASH=NONE; fresh faults stop the
cycle and are never cleared automatically. HOST controller tests cover an old
record present/absent, failed clear before Flash, corrupted new readback and a
fresh postboot crash. Firmware bytes and compiled ARM proofs are unchanged.
Older packages remain pinned provenance inputs until the complete successful
Spectrum and AI cycle; superseded build artifacts are removed afterward.

The November 13 clean install of 1BDB4385 / 161FEF7E passed full Flash readback.
AYABC stopped at 130 frames after 563 accepted blocks. The receiver reported
an invalid stop symbol with DMA complete, empty FIFOs and no PIO FIFO fault.
Audio primed in 16,594 µs, and the buffer never emptied. Two blocks exceeded
4,720 µs, with a maximum of 4,761 µs. The largest frame lag was 3,618 µs.
Battery, keyboard and I²C counters stayed clean. The other three short tests
and the long test remain pending.

The candidate 7ACE0AE4 / 7E555A73 uses GP6 for start and stop transitions.
PIO waits for the last stop and the high level on PC10 before the software
checks DMA completion and validates the complete frame with CRC. The PIO
model reproduced 33 stop errors with intact data in 72 cases on the old
receiver. The candidate delivered the exact payload in all 72 cases. A
delayed data edge still failed CRC. The earlier physical capture had the
same intact-payload signature, but the latest failure only recorded receiver
registers, so its exact waveform remains unknown.

The candidate arms UART receive before releasing ACK. It then restores the
I²C controller while M3 sends the completion, with the I²C lease still held.
ARM execution verified ACK ordering, rejection of truncated or corrupted
frames and resource cleanup. The platform sanitizer suite and the AI ARM
regression passed.

The 7ACE0AE4 installation passed readback. AYABC stopped after 73 measured
frames and 320 valid blocks with a frame validation error. Before the error
there were zero late audio blocks, underruns or frames delayed by over 1 ms.
The maximum block took 4,188 µs and priming took 16,604 µs. DMA finished the
failed receive with zero words left and empty, unstalled PIO FIFOs.

A second run copied the first invalid frame before the audio context was
released. The header, sequence 509, payload length 244 and padding were
valid. The received CRC was EECECCEE and the CRC of the received data was
6D6B0299. Running the same snapshot and stereo synthesizer on the host
reconstructed block 123. Its CRC, 50378A56, was present one group early in
the capture. The preceding 186 payload bytes also matched at that offset.
The final group resembled the I²C pin restoration sequence.

A PIO model with a delayed GP6 start reproduced all 268 captured bytes. The
375 ns sample crossed into the next GPIOB symbol, then the receiver locked
onto data transitions until it skipped one four-byte group. The model used
a 120 ns start delay and 16 ns GPIOC skew. Those values were model inputs.
No electrical trace was captured.

B1F4B802 / ECA8A1F1 moves the sample point to 250 ns. GP6 framing, the
2 Msymbol/s link, DMA, CRC checks and CPU clocks are preserved. The candidate
replayed the correct frame through 144 phase, drift and skew cases, including
150 ns late starts and 150 ns GPIOC data edges. The actual compiled ARM
receiver, scheduling, keyboard and AI tests and the platform sanitizer suite
passed. Static SRAM is 120,516 bytes and the heap is 108,860 bytes.

B1F4B802 was installed with a full verified readback. Its first short
AYABC run stopped after 17 valid blocks with error -46. The maximum valid
block took 4,157 µs, with zero late blocks or underruns. The failed receive
had no PIO FIFO or DMA fault. The four short tests remain incomplete.

One SD-only observer then captured a different failure signature. Its block
7 header, sequence 90 and length were correct. Independent host synthesis
matched every byte except bit 7 of byte 222, which was 00 instead of 80.
Restoring that bit gave the original CRC E2728DCE. That bit corresponds
to the PC10 to GP9 lane. The capture establishes the data error, while
its electrical duration and cause remain unmeasured. Both failed runs
removed their temporary files and returned to CALCULATOR/CLOSED/NONE
with CRASH=NONE, clean I²C counters and closed CDC/lease.

The HOST candidate 17058CB6 / F6343B1E samples each symbol at 187.5, 250
and 312.5 ns and votes each lane before the full CRC check. It receives
three words per four-byte group using the DMA buffer shared with UART.
The UART ring keeps its 512-byte bound and the decoded frame has separate
storage through the ACK/UART exchange. The complete audio context still
occupies 5,120 bytes. Static SRAM grew by 8 bytes for the retained counters
of disputed blocks and lanes, leaving 108,852 bytes of heap.

The codec checked every one of the 6,432 sampled bits in a full capture.
The PIO model covered 672 single-sample perturbations, the previous group
loss capture and 144 start/phase/skew cases. Actual compiled ARM checks
covered voted data surviving UART reuse, FIFO stalls, all previous cleanup
cases and replay of the captured bit error. Two or three bad samples of
the same bit were rejected by CRC. These HOST checks passed along with
the platform sanitizer, M3 sound and AI regressions. Physical testing of
17058CB6 is pending.

The unified candidate C529144E / 630315F7 incorporates the seven exact
PSRAM64 files from the hardware-tested AI build C31F0D5E. To fit both
changes, the NRZ decoder lives in the existing NRZ Flash section, leaving
the fixed math layout intact. Voting three packed words in parallel
reduced the receiver path from 10,817 to 10,018 ARM instructions in the
modeled maximum-length receive, compared with 3,595 for one sample.
This count covers DMA completion through frame validation. It does not
measure time on the device. Static SRAM is 120,540 bytes and heap is
108,836 bytes. The sealed combined build passed the same ARM, PIO model,
audio, platform sanitizer and controller checks.

C529144E passed full readback and booted at 125 MHz. The first AYABC
qualification stopped on the first rejected block. An observer run
accepted 14 blocks before the next failure, including three blocks with
sample disagreements on GP9. It captured all 804 bytes written by DMA.
The host independently decoded them and matched the receiver output
byte for byte. All differences from the original PCM were on GP9.

The failed byte was 00 instead of 80. At 187.5, 250 and 312.5 ns the high
nibble read [0, 0, 8] and the low nibble read [8, 0, 0]. Both transitions
arrived late. A simulated 280 ns rising delay and 220 ns falling delay
reproduced every raw capture byte. Those exact delays are model inputs
within the intervals observed at the sample points. The frame CRC remained
the original 3B5C12E7, and the corrupted frame was rejected.

The next pair uses 1.5 Msymbol/s with TIM4 at 48 ticks per symbol. Pico
samples GPIOB at about 334 ns and GPIOC at about 375 ns. The CPU clocks
stay at 125 and 72 MHz. A maximum-length transfer takes about 112 µs
longer on the wire. The decoder handles two words per group and still
validates the full CRC before ACK. The new wire-rate flag prevents use
with the earlier transmitter. The new M3 body differs by two bytes and
the permanent loader is byte-exact.

The 8B437154 / A33761F2 and 029BA093 pair passed the replay of the raw
capture and earlier group loss, 480 phase and lane skew cases, and
24 late pulse cases. Actual compiled ARM sender, receiver, loader,
keyboard and AI regressions passed. The package includes the previously
verified PSRAM64 sources. The two images require an on-device test to
establish the link and timing margins.

On 2026-11-13 both images passed readback. During the planned M3 restart
the Pico recorded 62 I2C aborts and controller resets. The new Pico booted
with zero I2C and battery errors. Cosmic Payback AY/ABC then completed 599
measured frames at 3.499999918 MHz (within the 1 µs timer uncertainty),
48.826 fps and 539 µs maximum frame lag. It accepted all 2,603 NRZ blocks
and 307,154 samples with zero CRC errors, underruns or I2C faults. Startup
was 17,873 µs. One block took 4,730 µs against the 4,720 µs limit, which was
the only failing check. The three other short tests and the long run are
pending. Both owned SD directories were deleted and USB ownership returned.

Block 1304 had a cached 11-byte request and 250 samples already queued.
The per-block Pico maxima were 589 µs between service calls, 333 µs in
receive/service work, 355 µs in the engine step and 19 µs in transmit work.
Those maxima are not additive stage timings. The module reported a run
mean of 1,924 µs per render, a 2,329 µs maximum job and a 1,564 µs maximum
slice. The module supplied no per-block render/schedule split in this run.
The nominal 670-symbol body is 447 µs at 1.5 Msymbol/s, excluding DMA chunk
setup, idle and ACK/READY exchange. The maximum M3 transport measurement
was 1,724 µs including handshake. Mean measured block latency was 3,816 µs.

Pico 7103F15A / 1265EBA4 packs only the selected lane bits in PIO, retaining
the symbol rate and sample positions used in the hardware run. A full frame uses 67 DMA
words instead of 134. The decode still copies into dedicated storage before
UART reuses the DMA buffer and validates the full CRC before ACK. The Pico
allows up to 8 µs for the M3's READY rise after ACK low before yielding back
to the worker. A later edge is still serviced on a later call. UART RX is
armed before ACK is released in both cases.

In the ARM model, full-frame polling from DMA completion through CRC and
READY_LOW took 3,545 instructions, down from 4,881. These are instruction
counts. The exact field captures replayed, the 480 split-phase cases kept
identical bytes, and the ARM model covered immediate, delayed and next-turn
READY as well as timeout and bus restoration. The platform, sound, keyboard
and AI checks passed. Package021 uses the installed M3 029BA093 and keeps
the strict deadlines. It is ready for a Pico-only update and a hardware
check at 125/72 MHz.

Pico 7103F15A passed a complete Flash readback and booted at 125 MHz.
AY/ABC again completed 599 measured frames and accepted 2,603 blocks,
with a maximum frame lag of 539 µs, zero audio underruns and zero NRZ or
I2C errors. Mean block latency fell from 3,816 to 3,784 µs and the minimum
queue increased from 134 to 156 samples. One late block remained at
4,732 µs. This was block 1981 rather than 1304, with a cached 11-byte
request and 264 queued samples. Its maximum service gap was 426 µs.
Qualification stopped at AY/ABC. The temporary directory was removed.

The SD diagnostic for Pico F6E637C2 / C03391DF uses the same audio driver
sources. It compares the ordinary AY.S3M with AYTIME.S3M, which returns
the synthesis time and the inter-slice gap in the existing result header.
The two modules produced the same PCM and oscillator state under the ARM
test. The test APP samples completed blocks from its own core and prints
histograms only after audio closes. It counts missing polls and rejects
misassociated results. It reports P50, P95 and P99 as 64 µs intervals and
retains the eight slowest captured blocks with an exact wall time. The
module's two times are rounded up to 16 µs, and the remainder includes
the UART, NRZ, receiver service and other non-render work.

Both diagnostic runs completed 599 measured frames and accepted all 2,603
blocks at 125/72 MHz. Each run had zero CRC, UART and I2C errors and zero
underruns. The maximum frame lag was 539 µs in both. The APP sampled 2,602
blocks in each run; the native counters also cover the final block.

| AY/ABC diagnostic | Control | M3 timing enabled |
|---|---:|---:|
| Strict result | PASS | FAIL |
| Startup, limit 20,000 µs | 17,835 µs | 20,408 µs |
| Block latency P50 | 3,712–3,775 µs | 3,712–3,775 µs |
| Block latency P95 | 4,096–4,159 µs | 4,096–4,159 µs |
| Block latency P99 | 4,288–4,351 µs | 4,288–4,351 µs |
| Maximum, limit 4,720 µs | 4,662 µs | 4,770 µs |

In the timed run, M3 synthesis was 1,920–1,983 µs at P50 and
2,176–2,239 µs at P99, with a maximum of 2,336 µs. Pauses between
synthesis steps were 0–63 µs at P50 and 192–255 µs at P99, with a maximum
of 256 µs. The remainder was 1,664–1,727 µs at P50 and 2,240–2,303 µs
at P99, with a maximum of 2,577 µs.

The only late timed block, 1532, used an inline 20-byte request. Its
4,770 µs comprised 2,128 µs of measured synthesis, 224 µs between its
steps and 2,418 µs of remaining exchange and service. The Pico recorded
a 751 µs gap between service calls during this block. Its largest pump,
engine step and TX times were 253, 332 and 44 µs respectively. These
peak values describe separate observations, so they cannot locate or
explain the gap by addition. Other blocks performed more synthesis or
spent more time in the remainder and still finished on time. The two
short diagnostics establish the split for the observed late block; more
runs are needed to characterize the rare worst case.

Both diagnostics ran from temporary SD files on the same Pico and M3
images. Their directories were deleted, and the device returned to
CALCULATOR/CLOSED/NONE. The PASS applies to one diagnostic AY/ABC run;
the four short qualification cases and the gated long run remain open.

An SD-loaded module candidate saves work when no tone, noise, or envelope
edge falls in the current sample. It uses an addition and preserves the
previous mixer state. Rare imported phases outside their period still
use the original update. The candidate fits in 5,960 of 6,144 bytes and
uses the same packet and state ABI.

Actual relocated Cortex-M3 code was compared against the original module
on 63 blocks from each of the four Cosmic Payback chip/layout combinations.
All 29,736 stereo results and 20 full state exports matched byte for byte.
Instruction counts fell by 5.62–5.63% per combination. On replay blocks
1304, 1532 and 1981, the AY/ABC counts fell by 5.90%, 6.30% and 8.94%.
These counts include the work of the relocated module; they are not
hardware measurements in microseconds. The native qualification limits
are unchanged.

The four SD-only Cosmic Payback short runs completed on the same
125/72 MHz resident pair:

| Chip / mix | Result | Worst audio block (µs) | Startup (µs) |
|---|---|---:|---:|
| AY / ABC | PASS | 4,570 | 17,852 |
| AY / ACB | PASS | 4,603 | 17,830 |
| YM / ABC | PASS | 4,542 | 16,605 |
| YM / ACB | FAIL | 4,454 | 20,473 |

All 10,412 blocks met the 4,720 µs deadline. There were zero CRC, UART or
I2C errors and zero audio underruns. Each run completed 599 measured
frames at 3.5 MHz within the timer's precision, with 539 µs maximum
frame lag. Against the ordinary AY/ABC diagnostic on the same Pico
build, average module render time fell from 1,924 to 1,820 µs per block.
YM/ACB failed only the 20,000 µs startup check. The long run was not
started. The temporary SD directory was removed and the device returned
to CALCULATOR/CLOSED/NONE.

Three subsequent YM/ACB diagnostics passed the strict counters, with
startup at 16,565, 17,851 and 17,853 µs. In the third, PWM DMA was
armed 903 µs before the guest audio clock started. The first sample
callback with the guest running arrived 515 µs after the gate. The
first three complete batches of guest events were visible by 5,256,
7,359 and 11,059 µs. The first three results were visible in the
native PWM queue by 10,153, 13,824 and 17,680 µs respectively.
Their native elapsed times were 3,944, 4,351 and 3,597 µs. The first
refill with PCM was at 18,368 µs relative to the guest gate.

The observer can only bound its sampled transitions. Its maximum gap
between polls was 1,607 µs, and it could not associate the intermediate
I2C/NRZ transitions with these requests or the exact first duty reaching
the PWM pin. The observer rejected request timestamps earlier than the
lease timestamp; the resident takes the timestamp before acquiring the
lease and reuses it when creating the request. The cause of the earlier
20,473 µs startup remains open.
The diagnostic results do not replace the standard YM/ACB short case.

The unchanged standard YM/ACB probe was repeated with exactly the same
resident pair, AY.S3M and game snapshot. It passed with 17,851 µs startup,
4,532 µs maximum block latency and 539 µs maximum frame lag. All 2,603
blocks were accepted with no CRC, I2C or UART errors or audio underruns.
The first YM/ACB failure remains in the original record. The other three
standard passes and this closed repeat satisfy the short-test gate.

The clean AY/ABC 30,000-frame test stopped after 12,000 measured frames
(245.76 s). There were 52,071 NRZ replies and pin returns without any
NRZ CRC, UART or I2C errors. Pico published 52,070 blocks; one result
was in flight when the PWM fault ended the test. The M3 audio queue
did not underrun. Frame lag peaked at 854 µs. The interrupted run did
not meet the complete-run or strict Z80 checks.

Nine audio blocks exceeded 4,720 µs. The first was block 16,782 at
4,917 µs: 26-byte inline request, 254 samples queued, 412 µs peak gap
between Pico service calls, 280 µs pump, 538 µs engine step and 128 µs
TX maxima. The module did not report a compute/schedule split for that
block. Separately, PWM raised error -31 after the DMA head reached
49 samples past the last completed refill. The DMA still had data;
its unchanged safety guard requires at least 16 unread samples
when a refill begins. This is one DMA refill deadline failure.

The prior timer target was 47,499,752 µs (low word). At the ARM
snapshot 47,499,803 µs, DMA had already read 16 samples beyond the
newly refilled cursor. The SDK scheduled the next alarm at 47,501,032 µs
by adding 1,280 to the previous target. The IRQ arrived 30 µs later
and the callback was another 60 µs after that. The saved interrupted PC
resolves to the SDK hardware timer IRQ, immediately after restoring
PRIMASK; the foreground site was worker UART service. DMA advanced to
47 samples at IRQ entry and 49 at the callback. This explains the
guard failure on this trace. It does not explain the nine late blocks.
USB and the device lease were closed and the test directory removed.

Pico candidate 7E432710 / 98893209 follows the sampled DMA head after
each refill when it schedules the next alarm. It keeps the 16-sample
safety guard. At the captured cursor position it schedules the next
alarm 680 µs after the callback, instead of advancing the previous
target by 1,280 µs. Replaying the captured 90 µs of additional delay
in the linked ARM code completes the refill. Forcing head minus
filled to 49 samples still fails the guard as before.

The same image copies a ready 32-sample half in contiguous chunks,
reading the APP running flag once per half. A short queue, startup or
an error still uses the sample-by-sample path. The host comparison
covered 36,417 states, including 31,184 fast-path states. In linked
RP2040 code the ready half took 400 instructions (417 across the
queue wrap), down from 1,129. The time this saves on the device,
including its effect on late M3 blocks, remains to be measured.

The candidate changes four audio files relative to the installed
F6E637C2 source snapshot. The exact candidate passed the audio, PWM,
NRZ4, I2C deadline and qualification checks under sanitizers.
The panel recovery test reports the same color scroll failure in
both source snapshots, with identical panel code, fixtures and logs.
The full platform run is therefore not green. Static RAM remains
120,532 bytes, leaving 108,844 bytes of heap. The UF2 reconstructs the
sealed BIN byte for byte and ends before the ROM cache and settings.
Acceptance requires four new AY/YM × ABC/ACB runs on the exact
candidate, then the 30,000-frame AY/ABC run with the same limits.

Pico 7E432710 / 98893209 was installed without a backup. All
1,793,244 bytes of the new image matched the readback. It booted
with BOOTS=38 and CRASH=NONE. The first USB ownership check timed
out before opening the port. A fresh check found the port free,
and the second attempt completed the only Flash write.

| Chip / mix | Result | Startup (µs) | Worst block (µs) |
|---|---|---:|---:|
| AY / ABC | PASS | 17,959 | 4,599 |
| AY / ACB | PASS | 17,931 | 4,567 |
| YM / ABC | FAIL | 20,521 | 4,545 |
| YM / ACB | PASS | 17,942 | 4,411 |

Each run measured 599 frames at 3.5 MHz within timer precision
and 539 µs maximum frame lag. All 10,412 sound blocks met the
4,720 µs deadline. The runs recorded zero PWM or M3 underruns and
zero NRZ4, UART or I²C errors. YM/ABC crossed the 20,000 µs startup
limit by 521 µs. The strict series stopped there. The separately
run YM/ACB test completed the requested set and the result is
3/4 PASS. The 30,000-frame run did not start. Both temporary SD
test directories were removed after use and the PicoCalc returned
to the calculator screen with CDC and the device lease closed.

The first keyboard bitmap request also pumps native display, USB and
keyboard services. Spectrum previously called it after starting the
guest clock and before executing any Z80 instructions. Earlier game
profiles recorded up to 1,876 µs for a keyboard request. This call can
delay publication of the first sound events. The failed YM/ABC run
contains no startup trace, so the time spent in that call is unknown.

For M3 audio, Spectrum now executes the first frame from the already
captured keyboard state and polls during the first pacing wait. The
normal polling cadence resumes after that frame. The host APP test
reproduced the old startup order and passed with the change on both
the menu and FILE_OPEN paths. The Spectrum suite with ASan and UBSan
passed. The product APP uses 49,040 of 49,152 bytes and uses the same
AY.S3M as the four earlier runs. The next qualification uses temporary
APP files on SD and the installed EBAAE560 / 5D1DFCF0 Pico image. Its
audio, display and I/O sources match 7E432710 byte for byte.

On EBAAE560, all four short tests passed at 125/72 MHz:

| Chip / mix | Startup (µs) | Worst block (µs) |
|---|---:|---:|
| AY / ABC | 16,674 | 4,511 |
| AY / ACB | 16,663 | 4,443 |
| YM / ABC | 16,675 | 4,604 |
| YM / ACB | 16,705 | 4,514 |

The same strict checks covered 10,408 blocks and 598 measured frame
intervals per run. There were no late sound blocks, audio underruns
or NRZ4, UART or I²C errors. Peak frame lag was 539 µs in all four
cases. The closed short test receipt admitted the 30,000-frame
AY/ABC run on the same builds.

The 30,000-frame run reached its planned stop. The probe measured
29,998 interior frame intervals, 2,150,256,504 T-states and
614,359,001 µs (3.5000000008 MHz, 48.8281 measured fps). Peak frame
lag was 543 µs, with no frame over the 1 ms limit. Audio started at
16,675 µs. PWM completed 480,015 refills with no underruns. M3
rendered and delivered 15,359,824 samples in 130,168 verified blocks.
NRZ4, UART and I²C error counters stayed at zero.

The strict result failed only the late-block check. Fifteen blocks
exceeded 4,720 µs. The first and slowest was block 7,098 at 5,099 µs.
It carried 26 bytes of input, produced 118 stereo frames and had
262 samples queued when completed. Its largest Pico service gap
was 493 µs. The stream-wide minimum queue was 118 samples. The
standard module provides no compute and scheduling split for this
individual block. The test directory was removed and the device
returned to the calculator screen with CDC and lease closed.

The long-run records contain one late-block detail. The index and
arrival time of the other fourteen were not recorded. They cannot
establish an interval distribution or connect a delay to a specific
LCD, I²C, PWM or keyboard operation. The 493 µs service gap is the
largest one recorded for block 7,098 and is not the sum of those stages.

A host replay of 130,168 blocks from the same Cosmic Payback snapshot
reconstructed a 26-byte, 118-frame block at index 7,098. The relocated
Cortex-M3 sound module matched 56,640 stereo samples and 20 full chip
states in five windows and four chip/layout combinations. In AY/ABC,
the reconstructed block took 70,268 module instructions. The median
of the 120 checked blocks was 65,877 and the maximum was 73,315.
The best of the tested compiler changes saved 297 instructions on
that block. This replay has no device interrupt timing and does not
identify a cause for the measured 379 µs overrun.

Two 3,000-frame diagnostics have been built for the installed Pico
image. They sample the spacing of published PCM results, keep the
polling uncertainty, and associate the slowest sampled results with
the Pico worker site, transport phase, I²C state and latest PWM IRQ.
The timed module also reports synthesis and pauses between its steps.
The actual relocated ARM observer passed the 5,099 µs fixture and
timer wrap checks. The timing module matched 3,584 PCM samples in its
ARM loader test. The diagnostics are ready for hardware measurement.

The paired hardware diagnostics each measured 2,998 frame intervals and
13,015 verified audio blocks on EBAAE560 at 125/72 MHz. Both reported
541 µs peak frame lag and zero underruns or bus errors. Startup was
16,695 µs with the standard module and 19,227 µs with timing enabled.
Both failed the unchanged late-block check.

The standard module had two late blocks. Block 5,848 was 4,811 µs.
Block 7,098, also late in the earlier long run, was 4,780 µs. The timed
module had one late block. For block 1,590, the 4,862 µs wall time
compared with 2,064 µs of M3 synthesis and 256 µs between M3 steps.
The remaining 2,542 µs includes UART, NRZ and work on both processors.
Pico recorded a 781 µs maximum gap between service calls in this block.
The observer also sampled M3 service while awaiting READY high, with
the PWM IRQ having run since the previous service. This sample does
not break the observed pause into PWM and foreground time.

The observer captured 13,014 results and 13,013 consecutive intervals
per case. The median observed interval was 3,840–4,095 µs for control
and 4,096–4,351 µs for timing. The respective longest observed
intervals were 9,713 and 10,789 µs. Observer polling gaps reached
2,554 and 2,636 µs. The sampled publication time can therefore differ
from the actual publication time by up to the recorded poll gap.
The completed run removed its temporary files and released the device.

A finer SD observer added side-effect-free snapshots of READY, ACK, the
UART receiver, I²C enable and the PWM IRQ's start, end and interrupted
PC. The playback of the 3,000-frame control case reached its planned
stop at 125/72 MHz, measured 2,998 interior frames and verified 13,014
audio blocks. There were no late blocks, underruns or bus errors. Peak
frame lag was 541 µs and the longest block was 4,580 µs. The same
strict check reproduced a startup miss of 21,780 µs against 20,000 µs,
so the controller did not launch the timed case. The device returned
to CALCULATOR/CLOSED/NONE, and the test folder, CDC and lease were closed.

The raw observer report remained complete and was parsed offline.
The slow control block 1,967 took 4,573 µs. Its capture found READY
high and ACK low with UART RX and I²C disabled, 801 µs after the last
recorded service end. The latest completed PWM IRQ accounted for at
least 84 µs (entry to post-handler snapshot); it had interrupted LCD
color window setup. The IRQ timing leaves the majority of the 801 µs
interval unaccounted for. Across this run the sampling gap peaked at
1,810 µs. The instrumented result leaves the rare steady-state delay
cause open.

A separate SD observer for the reproduced startup failure records the
guest gate, readiness of the first three event batches, the NRZ request
and GPIO lease times, publication and PWM fill. Native request stamps
may precede the lease timestamp because the service clock is sampled at
the start of the turn. The linked ARM observer covers that ordering and
timer wrap. The hardware package is ready for up to eight 600-frame
AY/ABC runs, stopping at the first measured startup above 20 ms.

The startup observer reproduced the miss on attempt six. The first
four runs passed at 16,638–16,693 µs. Attempt five started in
16,669 µs and had one 4,743 µs block. Attempt six started in 20,349 µs
and also had a separate 4,932 µs block later in the run. Each run
had zero audio underruns and transport errors. The controller stopped
on the first startup miss and released the temporary directory, USB
and lease.

In the failed startup, the second event batch was visible at 6,591 µs
after the gate. The first block finished at about 8,841 µs. The next
attempt to borrow I²C was recorded at 9,288 µs. The observer sampled a
busy I²C slot at 9,467 µs. The second request started at 12,383 µs and
completed 3,749 µs later. The 3,095 µs delay before its start occurred
while competing for the keyboard/PMU pins. The third block completed
at about 19,745 µs, and the first PWM refill with PCM was at 20,682 µs
relative to the guest gate.

The Pico candidate holds off new nonblocking keyboard/PMU requests
during NRZ4 priming. It lets in-flight transfers complete and releases
the hold after the existing three blocks have arrived, after 25 ms,
or when audio stops or fails. Explicit blocking peripheral operations
use their usual queue path. The linked ARM test checks the old
admission, new gate, existing I²C ownership, both PCM layouts and
timeout across a timer wrap. This change targets startup; the
steady-state late-block limit still needs hardware qualification.

F5288532 / 127B8B8C passed the linked ARM admission and NRZ4 tests,
host I²C/keyboard/power checks and the Spectrum suite with sanitizers.
The image has 108,844 bytes of resident heap. It is awaiting
approval and a board run with four short chip/mix combinations.

Harness then installed the PSRAM diagnostic image 1B0010C3 / CC10489A.
The same four-file startup patch was rebuilt on that verified snapshot
as B3821DD4 / A4C12DE2. Its linked ARM admission and NRZ4 tests passed.
The newer Harness sources are included. This is the active hardware
candidate and remains untested on the board.

On 14 November, PicoCalc booted B3821DD4 / A4C12DE2 at 125 MHz.
The one Pico Flash write used no backup. A full readback of the
1,793,244 newly written bytes matched the image. STM32 M3 remains
029BA093 at 72 MHz. The short qualification uses the same four
AY/YM and ABC/ACB fixtures and the original startup and block limits.

All four short Cosmic Payback cases ran on B3821DD4 / A4C12DE2
at 125/72 MHz. Each measured 598 interior frames and verified 2,602
NRZ4 blocks.

| Chip / mix | Strict result | Startup (µs) | Worst block (µs) | Blocks over 4,720 µs |
|---|---:|---:|---:|---:|
| AY / ABC | PASS | 16,627 | 4,633 | 0 |
| AY / ACB | FAIL | 16,690 | 5,214 | 2 |
| YM / ABC | FAIL | 16,699 | 4,827 | 2 |
| YM / ACB | PASS | 16,668 | 4,700 | 0 |

All four startups met the 20 ms limit, including the previously failing
YM/ABC case. The Z80 sustained 3.5 MHz within timer precision and peak
frame lag was 539 µs. There were no underruns or NRZ4, UART or I²C
errors. The two failures were solely due to late blocks. The long run
was not started because the unchanged gate requires all four PASS.
The test folder was removed and the device returned to
CALCULATOR/CLOSED/NONE with the CDC and lease released.

The diagnostic AY/ACB and YM/ABC runs on FD575985 / 0ACC9997 at
125/72 MHz used the timed module for 3,000 frames per mode. AY/ACB
had no late blocks across 13,015 results (maximum 4,690 µs).
YM/ABC had one late block, #5,223 at 4,887 µs, with 260 samples already
queued. Its measured M3 synthesis took 1,888 µs and the gaps between M3
steps took 48 µs, leaving 2,951 µs outside those steps. A snapshot in
that block showed Core 1 expanding an LCD strip while NRZ4 was in TX
and the pins still belonged to UART and I²C. The snapshot identifies
the state at that moment, not the duration of the entire LCD operation.
The entire runs differed by 261 µs of M3 render time. The runs had no
underruns or bus errors; their maximum frame lag was 541 µs.

The next Pico image, 2413366F / D46C4CDA, defers packing the next event
block until the current receiver is armed, enables Core 1 DMA wakes
for completed NRZ4 captures and services the transport during fallback
LCD scanline waits. The fault path masks DMA completion around the
abort and still validates the final stop edge, CRC and matching UART
reply as before. The colour and FFN base and its 108,792-byte SRAM
heap remain the same. Host Spectrum and audio suites and linked ARM
tests passed. This candidate uses the same strict qualification
limits and the original untimed module for the four short cases.

All four on-device tests completed. AY/ACB, YM/ABC and YM/ACB passed
with maximum block times of 4,531, 4,459 and 4,553 µs. AY/ABC block
#225 reached 4,842 µs; 256 PCM samples remained queued. There were no
underruns, bus errors or frame delays over 1 ms. The long run gate stayed
closed.

The next experiment loaded a 6,120-byte M3 sound module from SD on
BFDD4DB7 / 8F167872. It uses the simplified unity-gain stereo PWM mixer
when the second PSG is silent with no events and both DACs are constant.
The same 480 reconstructed game blocks returned bit-identical PCM and
state, with 6.32–6.36% fewer M3 instructions at the median and 5.59–5.61%
fewer at the maximum. The three sanitizer tests covered both chips,
stereo layouts, mono, PCM16, dynamic DACs and changing envelopes. The
linked module also passed 64 relocated M3 jobs.

With 2,602 blocks in AY/ABC, M3 render time fell from 4,734,875 to
4,386,894 µs (7.35%). The four strict NRZ4 cases on the new module had
maximum block times of 4,542, 5,099, 4,551 and 4,717 µs in
AY/ABC, AY/ACB, YM/ABC and YM/ACB respectively. AY/ACB failed on block
#537 with 240 samples still queued. This block included a Core 1
audio-engine step up to 938 µs. That measurement includes time
preempted by IRQs and cannot by itself locate the slow instruction.
The temporary files were removed. There were no Flash writes,
underruns or frame delays over 1 ms. The long run gate remained closed.

The UART path committed in 93a3c0908 already passed the earlier
30,000-frame run with no late blocks and a maximum of 4,588 µs, using
different Pico and M3 images. To isolate the transport on the current
unified base, the UART control build uses the same game and module as
the latest NRZ4 experiment, leaves the STM32 BIOS installed, and checks
that PCM is returned through UART without borrowing the I²C pins.

The control booted as 98F714C7 / CB19CBF6. Its programmed image was
verified by readback. All four 600-frame cases used the same
`AY.S3M` as the latest NRZ4 series. The old and new runs each use
125/72 MHz and 24 MHz LCD SPI. The maximum remains a strict
4,720 µs limit for 118 stereo frames.

| Chip / mix | NRZ4 mean (µs) | UART mean (µs) | NRZ4 max (µs) | UART max (µs) | UART result |
|---|---:|---:|---:|---:|---|
| AY / ABC | 3,514 | 3,667 | 4,542 | 4,544 | PASS |
| AY / ACB | 3,511 | 3,668 | 5,099 | 4,569 | PASS |
| YM / ABC | 3,517 | 3,670 | 4,551 | 4,568 | PASS |
| YM / ACB | 3,511 | 3,665 | 4,717 | 4,522 | PASS |

All UART cases reported zero late blocks, underruns, bus errors and
frame delays over 1 ms. The faster NRZ4 path saved a mean of about
154 µs per block. Its worst block exceeded the deadline. These short
UART tests admit a 30,000-frame run with the same firmware and module.

The archived UART qualification used a different module with lossless
stereo pair repeats. Replaying its exact `AY.S3M` produced the same
samples and state on all 480 reconstructed blocks, while reducing its
244-byte result to 69–85 bytes on average, depending on AY/YM and mix.
That makes the historical mean latency unsuitable as a direct transport
A/B. The present A/B uses raw PCM on both paths. The optional updated
repeat module fits in 6,008 bytes and produces the same result lengths
and decoded samples; its median instruction count was 1.82–1.93%
lower than the archived repeat module. The short and long UART
qualification here uses the tested 6,120-byte raw module.

The raw UART long run completed 30,000 frames (29,998 interior frames,
614.359001 s). Its 130,168 blocks included 21 above 4,720 µs; the
maximum was 4,921 µs. The first late block, #537, was 4,778 µs with
240 samples queued. That same game block was late in the NRZ4
AY/ACB run. Frame lag peaked at 543 µs and the Z80 sustained 3.5 MHz
within timer precision. No audio underruns or peripheral errors were
recorded. The strict run is a failure, and the temporary files, CDC
and lease were released. The UART short PASS does not qualify a
replacement for the previously measured compressed UART path.

On the same 98F714C7 / CB19CBF6 Pico and 029BA093 M3, with no
reprogramming, the updated 6,008-byte lossless repeat module then passed
all four short cases. The worst AY/ABC, AY/ACB, YM/ABC and YM/ACB blocks
took 4,331, 4,344, 4,408 and 4,233 µs respectively. UART accepted
79–92 bytes per block, including framing, compared with around 270
without compression. Startup fell from about 16.7 to 12.8 ms. Each case
ran at the same 3.5 MHz Z80 pace and had zero late frames, late audio
blocks, underruns and bus errors. The repeat module was then admitted
to a separate 30,000-frame run.

The repeat UART run completed 30,000 frames with the same Z80 timing
and 543 µs maximum frame lag. Nine of 130,169 blocks exceeded the
unchanged limit, compared with 21 of 130,168 in the raw UART run.
Its first late result, block #7,098, took 4,773 µs with 198 samples
queued. The maximum was 5,079 µs. The average fell from 3,689 µs
without repeats to 3,006 µs with them; UART traffic fell from about
270 to 101 received bytes per block including framing. There were
zero underruns, lookups for readiness, NRZ4 blocks or bus errors.
Both long runs therefore fail strict qualification. The original
compressed UART qualification is still the only passing long result
in this comparison. The repeat run used no Flash writes and returned
CALCULATOR/CLOSED/NONE with the owned SD directory removed and CDC
and lease closed.

## Final transport comparison

With the faster mixer and lossless compression enabled for both transports,
UART passed three of four short cases and variable-length NRZ4 passed two.
UART delivered the average block 192–234 µs sooner. The late cases kept the
long-run gate closed on the experimental BIOS. The same mixer's compressed
UART path later passed all four short cases and 30,000 frames on the stock
KEY25 BIOS. See the [final comparison and UART measurements](picocalc-spectrum-uart-20261114.md).
