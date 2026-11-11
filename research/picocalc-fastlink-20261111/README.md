# PicoCalc synchronous-link experiment

This is a finite RAM diagnostic, not a replacement production transport.
Pico runs at 125 MHz, STM32F103R8 at 72 MHz. Neither firmware is flashed.
The APP requires the exact reviewed resident `7C38C634 / 8A17554E` because it
binds that ELF's SDK resource-allocation functions. It checks the function
bytes and firmware footer; the controller also verifies native firmware CRC.

The read-only identity module validates M3 metadata and calculates the BIOS
body CRC in 128-byte cooperative steps. Pin changes are admitted only for
the known `3BE158B4` BIOS and its stock clock configuration.
The guard also requires the Cortex-M3 CPUID and 64-KiB factory Flash size.
Zero `DBGMCU_IDCODE` is expected without a debugger on this chip, as described
in ST ES096 Rev15 section 2.2.2; a readable conflicting device ID is rejected.

| Mode | Clock | Data | M3 work during transfer |
| --- | --- | --- | --- |
| UART reference | asynchronous | PC10 → GP9 | resident UART DMA |
| Two-wire GPIO | PB8 → GP7 | PB9 → GP6 | software, interrupts enabled |
| Four-wire GPIO | PB9 → GP6 | PB8/PC11/PC10 → GP7/GP8/GP9 | software, three bits per clock |
| Two-wire timer/DMA | PB8 → GP7 | PB9 → GP6 | TIM4 update → DMA1 channel 7 → GPIOB BSRR |

PIO0 follows external clock edges and packs 24 bits into each RX FIFO word.
An SDK-claimed DMA channel copies those words to SRAM. Pico does independent
arithmetic while receiving. The M3 DMA variant similarly performs independent
arithmetic while the peripheral sends its prepared waveform. These counters
demonstrate available execution capacity; they are not CPU-utilization or
energy measurements.

The GPIO-DMA waveform uses two 32-bit BSRR writes per bit plus an idle tail:
24 payload bytes require 1,540 waveform bytes. Encoding time is recorded
separately. Timer targets of 1, 2, 4.5 and 9 Mbit/s are not measured rates:
bus contention may stretch GPIO clock intervals. Hardware `wire_us` and
`wire_cycles` cover the sender's transfer and completion observation. They
provide a conservative effective payload rate, including observation cost.

The fixture deliberately waits 500 µs before taking the pins, restores Pico
by 2,500 µs and defers the M3 result until 4,000 µs. `total_us` includes those
guards and must not be presented as production audio latency. A production
candidate would additionally need bounded arbitration with keyboard I²C,
waveform-memory accounting and an audio-load qualification.

Each M3 call restores its hardware before returning to the BIOS main loop.
After GPIO use, I2C1 restoration follows the verified open-drain transition
sequence in ST ES096 section 2.8.7, then applies I2C1 SWRST and restores the
saved address/timing/control registers. Before/after status is returned in
the diagnostic reply. This is a candidate recovery measure: the exact cause
of the observed hardware timeout still requires the new status measurements.
The local transfer budget is 1 ms, and the runtime slice limit is 2 ms.
Interrupts stay enabled, so these limits detect overruns rather than making
an unconditional execution-time guarantee against arbitrary interrupt load.
TIM1/2/3, PMU I²C2, Flash and clock settings are untouched. Four-wire mode
temporarily borrows the existing UART pins after the control request has
finished transmitting. The first failed case stops the run.

## Reproducing HOST checks

The controller-policy suite needs only Python 3 and the checked-in fixtures:

```sh
python3 research/picocalc-fastlink-20261111/controller_test.py
```

It supplies a synthetic C5 status and APP plus an in-memory protocol backend
to the real controller logic. It imports no archived hardware backend and
opens no serial device. Its result is written under `.build`, not into Git.

The ARM suite additionally needs ARM GCC 14.2.1, its matching GDB/objcopy,
Unicorn 2.1.4, Pico SDK commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`,
and the exact archived resident ELF plus `manifest.json` for build
`7C38C634 / 8A17554E`. The ELF SHA-256 is
`75ef19a5237b0ed25357424e1fd31da2aa64c69fa98683b4300dc7f553ffce16`.
This firmware-specific suite requires that input; rebuilding a different
resident from current `main` is not a substitute. The ELF/build outputs are
local prerequisites and are not stored in this research directory.

```sh
python3 research/picocalc-fastlink-20261111/build.py \
  --resident /absolute/path/to/firmware-candidate \
  --toolchain /absolute/path/to/arm-toolchain/bin \
  --pico-sdk /absolute/path/to/pico-sdk \
  --output .build/picocalc-fastlink-20261111/kit-010
python3 research/picocalc-fastlink-20261111/host_test.py \
  --kit .build/picocalc-fastlink-20261111/kit-010
```

Use the Python environment with Unicorn installed for the last command.
On sandboxed macOS the repository's Unicorn prerequisite check may require
the normal approved execution route. HOST tests execute actual relocated
M3 ARM code, independently decode modeled pin transitions, inject faults and
execute Pico guards/restoration and the exact resident SDK allocators. Model
time is not hardware time. The build records the supplied resident path/hash;
the ARM suite reads that manifest rather than guessing another local ELF.

`fixtures/legacy_module.c` is the historical failing restoration code, built
only for the HOST regression. Its package SHA-256 must be
`245d2f7d09004d9977d0b14b99e39f84513bea440bad1a52e1ae5da231e8a84a`.
It is never embedded in the APP or uploaded. No old `.build/kit-004` binary or
old CDC log is needed for these HOST checks. The BIOS identity fixture uses
the existing tracked `firmware/picocalc-m3-boot` binaries.

## Session-specific hardware controller

`hil.py --prepare` creates the hash-pinned package for coordinator review.
Hardware mode requires a fresh grant for that exact package, holds the shared
root lease continuously, writes only a new `/FLTEST20/FASTLINK.APP`, then
checks and removes its own file and directory. Final health, counter deltas,
CALCULATOR/CLOSED/NONE, termios, CDC and lease closure are recorded. It has no
Flash, MCU-reset, ROM-mode or firmware-recovery action.
An application failure or changed I2C/keyboard health remains a failed
qualification; it does not prevent cleanup of the byte-exact owned SD file.
A changed file or foreign foreground is preserved and reported.
The current admission is scoped to the independently logged read-only Harness
handoff: BOOTS=19, BOOT_WATCHDOG=0, RESET_REASON=00010001, CRASH=AVAILABLE.
Those observed values are retained verbatim and must remain unchanged through
final status; any new reset fails qualification. The pre-existing crash record
is never cleared. The Harness receipt, before/after status, crash bytes and
preceding failed-run provenance are hash-pinned in the package. Package 008's
HOST-only admission change and package 009's Pico diagnostic instrumentation
preserve both M3 modules byte for byte. Package 010 changes HOST test inputs
and import/build paths only; its APP and current M3 modules are byte-identical
to package 009.

The HIL scripts require the archived local `current_hil.py`/`device_guard.py`
backend, historical receipts and the existing root device lease referenced in
`hil.py`. They deliberately do not manufacture that session's admission or
grant on a clean checkout. `cleanup.py` preserves the earlier cleanup-only
procedure for `/FLTEST14`; it is not the controller for a new test. Old grants
are never reusable. Preparing a package is a HOST file operation; hardware
access requires fresh review and a grant for its exact hashes.

Before borrowing I2C pins, the APP first lets ordinary native service complete
the entire keyboard transaction, including the 16-ms gap between selecting a
register and reading its response. Hardware BUSY=0 during that gap does not
mean the logical transaction is finished. This diagnostic reads `pending_`
and `io_phase_` at ELF/DWARF-pinned addresses of the exact resident build;
it never writes those private fields. A 100-ms limit rejects an overrun before
pin acquisition. After both fields reach zero, no service runs until the
physical idle fence, transfer and complete restoration have finished.

The native observer samples the exact ELF's timeout/reset/abort/keyboard-error
counters plus worker stage/result and keyboard pending/phase/online. It only
reads resident memory. A pre-existing nonzero counter is retained as baseline;
the first change latches the previous and current snapshots, stops new cases,
and is printed after resource restoration. The original pending UART reply is
drained before unloading the module. There are no counter clears or new timing
budgets. Boundaries are 1 before the logical fence, 2 after each service inside
it, 3 after the logical fence, 4 after the physical fence, 5 after pin restoration
before any service, 6 after the first post-restore service, 7 after key polling,
8 during module-load service, and 9 after cleanup. The readout is sequential,
not an atomic snapshot across cores; its first changed field brackets the
fault between observation points rather than identifying an individual bus edge.

## Measured result and remaining failure

Hardware run 008 at stock 125/72 MHz verified all 91 transfers and 3,192 payload
bytes, with zero capture/UART errors and correct CRCs. Its **overall result is
HOLD**: native I2C timeout/reset counters and keyboard errors each grew 0→7.
The logical fence did not solve this; it waited up to 19,234 µs, with service
calls in seven cases. M3 entry/restore flags and before/after SR1/SR2 remained
zero. Aggregate counters do not identify the exact failing boundary; the new
read-only native observer has passed HOST tests but has not run on hardware.

| Mode | Payload | Effective payload rate | M3 preparation |
| --- | --- | --- | --- |
| Software clock + one data line | 96 B | 1.240–1.244 Mbit/s | 44–65 µs |
| Software clock + three data lines | 96 B | 1.582–1.588 Mbit/s | 45–66 µs |
| Timer/DMA clock + one data line | 24 B | up to 3.121 Mbit/s | 108–115 µs |
| UART reference, nominal 2.25 Mbaud 8N1 | any | 1.8 Mbit/s theoretical payload ceiling | not a measured GPIO interval |

Raising the DMA timer target from 4.5 to 9 Mbit/s did not raise its measured
ceiling above about 3.12 Mbit/s. Preparation and ownership-turnaround costs
must be included before claiming an audio improvement over UART. No sustained
audio-load or energy advantage has been demonstrated.

Earlier failed runs remain failed: 001 rejected an allowed zero DBGMCU ID;
002 misread normal raw PIO status as an interrupt reservation; 003 exhausted
the original idle wait; 004 exposed a latched M3 I2C state and two native
timeouts; 005 stopped at intake on a pre-existing watchdog tuple; 006 passed
all data cases but added seven native timeouts. Package 007 was not run after
its admission became stale. None of those results is relabeled as a pass.
Run 008 removed its own SD directory, returned CALCULATOR/CLOSED/NONE and
closed CDC and the root lease. Neither MCU was flashed or reset.

Current HOST results: 100 relocated sender cases, 10 injected faults, 17 full
pin-acquisition scenarios, 36 native-boundary/counter injections, 29 exact
resident SDK allocator checks, plus identity/PIO/physical-idle/restoration
checks. Controller policy passes 11 admission cases, 12 native-frame cases
and three faulted cleanup workflows. These are model results, not a hardware
qualification. The four-data-line NRZ proposal is not implemented here.
