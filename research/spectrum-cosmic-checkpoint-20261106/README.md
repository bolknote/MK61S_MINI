# Spectrum / Cosmic Payback latency checkpoint

This preserves unfinished Spectrum work at the user's request to commit it.
The ordinary APP and production sources are unchanged. The candidate is an
patch against `9b61498e95a207bd30bf339f7e0c00b1029523a5`, with its
HOST checks, hardware measurement records and the separate silence diagnostic.
The target of original Spectrum speed, timely frames and audible sound remains
open. No hardware access took place while creating this checkpoint.

The original commit ID is recorded in `checkpoint.json`. The verifier uses
the base in the rewritten history and checks the source hashes captured
with the original patch.

## Candidate and qualification

`candidate.patch` contains the actual APP frame/audio scheduling changes,
consumer timing counters, exact weighted AY mixing and fourteen changed/new
source/test files. It keeps the existing Z80 core and memory model, both AY
chips, 25kHz samples, the chip clock, quality and ABI. The APP freezes each
completed image/palette/border before prefetching normal512T CPU chunks during
frame pacing. The extra prefetch has a4ms simulated wall-ahead guard and a queue
reserve for up to94 events per normal512T call. A normal instruction call is
bounded by556T; ignored DD/FD prefix chains are an explicit unbounded exception.

The weighted mixer replaces repeated signed filter steps by the exact identity
`outN=(out0+sum(mix[i]*2^i))>>N`, with oscillator/noise masks and three32-bit
multiplies when amplitudes stay fixed. The original per-tick path remains the
fallback. Four inactive error strings are shortened to fit the full diagnostic.
The ordinary candidate uses47528 SRAM bytes; the complete paced diagnostic uses
49148 of49152 bytes (48KiB), leaving4 bytes. These are build results, not a
hardware throughput or audibility qualification.

Saved HOST evidence includes524280 exhaustive filter identities and817792
sample-by-sample full PSG state comparisons. The actual APP scheduler with real
Z80/AY matches the production per-tick AY plus outer512 reference for all CPU
fields, RAM, video, both PSG states, ordered events and complete PCM trajectories
in Manic Miner, Cosmic Payback and Ianna (3100 captured frames each), plus a dense
80-frame keyboard/noise test. An input shift of1000T changes the trajectory.
These use simulated native costs and timestamped guest input; they do not prove
physical input latency. Three APP ROM modes and the scheduler/queue/frozen-image
tests passed ASan/UBSan. No weighted AY hardware run has occurred.

## Hardware measurements

The matched pair below uses the previous AY candidate, native2483E8A7/22F8ED32,
RP2040 at125MHz,100 warmup frames and every one of ten adjacent300-frame windows.
All3000 measured frames remain included. Pentagon has71680T/frame, so3.5MHz
corresponds to48.828125fps. API accepted submissions do not measure physical LCD
scanout or speaker output.

| Complete interval | WAIT-v2 | PIPE-v2 |
|---|---:|---:|
| Cycles / wall microseconds |215040407 /61439895|215040409 /61440117|
| Conservative lower MHz bound (wall+1us) |3.500012548849367|3.4999999348959583|
| Strict lower bound reaches3.5MHz |yes|no|
| Frames ready late / worst lateness |1879 /4696us|947 /5047us|
| Late sound events / worst delay |6512 /13908T|2623 /14106T|
| Produced-history deficit, max |16156T|17418T|
| Accepted / busy API submissions |2857 /144|2869 /132|
| Largest accepted submission gap |307358us|307382us|

Prefetch reduced the late-event count, but the roughly4ms worst sound delay and
307ms submission gap remain. Neither result establishes the requested outcome.
The PIPE-v2 nominal ratio is3.4999999918619946MHz; it is not rounded up to claim
the strict lower-bound check passed. Both v2 runs ended in verified native mode,
removed their temporary files, closed all CDC sessions with no errors, proved
no holders and reaped their supervisor child with exit0.

`PIPE-v1-717` is a historical result on another native build. Its old observer
prints DONE before the last API timestamp, so that endpoint contains marker
overhead. It is not an equivalent matched control for v2. Earlier unsuccessful
CPU/publication candidates are recorded in `experiment-history.json`; they are
not part of the selected code patch. PASS in a hardware receipt means the
bounded run and cleanup succeeded, not that performance or audible sound passed.

## Reported silence

The user reports hearing no sound. HOST Cosmic PCM is nonzero, but the actual
saved master volume and amplifier/speaker output are still unknown. Native
master volume0 permits successful callback generation while PWM stays128/128.
This is a hypothesis to test, not an established cause. Audio has not been
implemented on STM32; synthesis/mixing still runs on the RP2040.

`audio-check/` preserves SPAUDCHK source, five actual APP HOST scenarios, seven
controller tests, the PCM level report and the bounded controller for review.
The probe reads master volume without changing it, then requests2s silence,
2s left500Hz,2s right1000Hz,2s both and.5s silence through the existing native
audio API. It reads PWM/pinmux registers and closes the stream before its stack
context expires. At master10 the expected PWM extrema are96..160. An operational
PASS at master0 explicitly reports mute and cannot establish audibility.

This diagnostic has not run on the device. Its historical controllers retain
their original local paths. Do not run them directly from this archive. Fresh
supplier release, current firmware/binding review and a new exact Root phase GO
are required for any device run. Expired grants are omitted. Human confirmation
of the two tones is separate from callback and register evidence.

## Verification and contents

```sh
python3 research/spectrum-cosmic-checkpoint-20261106/verify.py
python3 research/spectrum-cosmic-checkpoint-20261106/verify.py --replay-host
```

The verifier checks the complete manifest, candidate/base hashes, all ten
adjacent windows and the strict timing calculation. The optional HOST replay
materializes only needed files from the pinned Git base into a temporary
directory, applies the patch there, and runs the exact filter/PSG, scheduler,
presentation, profile and audio lifecycle tests with ASan/UBSan. It performs no
device I/O, network access or primary source/index changes. Saved three-game
equality reports are historical results; replay of the six local tests is not
a new three-game campaign.

`provenance.json` binds copied records to their original paths and hashes.
Measurement text retains exact metrology lines, omitting game framebuffer bytes;
the original full-record hash and extraction prefixes remain recorded. Sources,
test/build reports and three measurement receipts are preserved. APP/ELF/UF2
binaries, ROMs, snapshots, disk images, old calculator/Flash state backups and
unrelated AI/math work are omitted. Installing an ordinary candidate, checking
two games on hardware and fixing the reported silence remain pending.

Local Git whitespace attributes preserve embedded patch context and the exact
CRLF endings of CDC measurement records; they do not affect production files.
