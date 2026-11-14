# PicoCalc GPIO-link experiments

Finite RAM diagnostics at stock Pico125MHz / STM32F103R8 72MHz. These are
transport experiments, not a replacement production audio backend. Neither
MCU is flashed or reset. Generated binaries, raw receipts and grants stay in
`.build`; checked-in `RESULTS.json` records compact outcomes and receipt hashes.

The [game-audio results](../../doc/measurements/picocalc-spectrum-uart-20261114.md)
use compressed UART. The [LCD DMA wait experiment](lcd-dma-wake.patch) is
preserved for replay. Its NRZ4 candidate still missed a deadline and the
wait change is inactive in the resident firmware.

## Results

| Run | Transport | Qualification | Native error delta | Result |
| --- | --- | --- | --- | --- |
| 013 | Clocked matrix | 91 cases, 3192 bytes, 84 GPIO leases | 0 | PASS |
| 014 | Clocked matrix, 100 cycles | 9100 cases, 319200 bytes, 8400 GPIO leases, 271.617s | 0 | PASS |
| 015 | First NRZ4 candidate | First NRZ block valid; next job refused dirty TIM4 state | 0 | HOLD |
| 016 | Corrected NRZ4 | 91 cases, 5208 bytes, 84 GPIO leases | 0 | PASS |
| 017a | Original NRZ4 packer, C99 resident | 91 cases, 5208 bytes, 84 GPIO leases | 0 | PASS |
| 017b | Faster NRZ4 packer, same C99 resident | 91 cases, 5208 bytes, 84 GPIO leases | 0 | PASS |
| 018 | Faster NRZ4, 100 cycles | 9100 cases, 520800 bytes, 8400 GPIO leases, 272.007s | 0 | PASS |

All successful cases pass byte-exact capture and CRC. Runs013/014 preserve
I2C timeout/reset/keyboard-error counters at9; they are not cleared to zero.
The earlier failed hardware runs remain failed. Runs013–016 preserve BOOTS19,
watchdog0, RESET_REASON00010001 and the pre-existing CRASH=AVAILABLE.
Harness separately installed C99DE0AF/528F4874 before017a, advancing BOOTS to20
and restarting native error counters at0. Runs017a–018 preserve that new intake
tuple and counters0→0; these diagnostics perform no Flash writes or MCU resets.
Every run above removes its own SD file/directory and records native
CALCULATOR/CLOSED/NONE, CDC closure and shared-lease closure.

For96-byte NRZ4 blocks, measured useful rates are:

| Four-bit symbols/s | Useful payload rate | Waveform preparation |
| --- | --- | --- |
| 1million | 3.182–3.188Mbit/s | 242–265us |
| 1.5million | 4.735–4.750Mbit/s | 243–262us |
| 2million | 6.234–6.307Mbit/s | 242–263us |

These rates use M3 DWT cycles for the transfer plus completion observation.
They include start/stop framing but exclude preparation and ownership guards.
The earlier two-wire timer/DMA transfer topped out around3Mbit/s. M3 UART at
nominal2.25Mbaud8N1 has a theoretical payload ceiling1.8Mbit/s per direction.
Preparation is still substantial; the wire improvement is not a claim of an
end-to-end audio or battery improvement. Those preparation measurements are
from016's original packer. Run018 now also qualifies NRZ4 over272.007s.

### Faster waveform preparation

The original packer recalculated the frame position for every symbol, including
a division. The new `nrz4_pack.h` walks four-byte frames directly and uses a
four-entry,16-byte BSRR lookup table. PortC words are PortB words shifted by2.
The complete M3 module is5896/6144bytes,48bytes more than the reference.
DMA scheduling, framing, receiver and interface restoration are unchanged.

The A/B reference module rebuilt from `fixtures/nrz4_reference.h` is byte-exact
to hardware016, SHA256 `d245744120a79d96a1daccf2b490f29d77624d1bbb035c02983a2755d7e568b6`.
Both A/B APPs bind to the same verified C99 resident and run at125/72MHz.
For96-byte blocks at2million four-bit symbols/s:

| Measurement | Original017a | Faster017b |
| --- | --- | --- |
| Preparation, including fixture pattern generation | 243–264us | 109–128us |
| Wire plus completion observation | 122–124us | 122–123us |
| Preparation + wire, median useful rate | 2.066Mbit/s | 3.236Mbit/s |

Paired active-time speedup is1.53–1.58×, median1.56×. The comparison excludes
GPIO ownership and deliberate readiness/reply guards; it is not production audio
throughput. Across all three short-test rates, preparation is241–265→109–129us.
The long run completed9100 cases and8400 planned I2C returns, max7us each,
with zero new I2C/UART/data errors. Its maximum M3 runtime slice was455us,
under the2000us cap. At2million symbols/s, its96-byte preparation range is
108–147us and wire range122–126us, including IRQ variation.

## I2C failure and correction

Runs011/012 localized the native timeout after a successful GPIO burst: the
next keyboard register-select write sat in Pico's TX FIFO while the master
reported no activity. Both physical lines were high. M3 had ACK/listen enabled,
CR1=0x401, CR2=0x324, HAL LISTEN=0x28 and no HAL error. Thus it was not an M3
slave holding the clock low. The controller stops at the first native delta.

Simply restoring the GPIO mux and I2C enable bit did not restart this master.
`restore_pins()` now returns the GPIO mux first, asserts/releases only Pico's
I2C1 peripheral reset bit through atomic aliases, then restores16 saved idle
configuration registers and the previous enable state. Both waits are bounded
at100us. Native RAM/request fields and software error/reset counters are never
patched. Planned interface restarts are counted separately in `FL RESTORE`.
Run014 completed8400 such returns with a maximum measured8us and no new error.
This is a peripheral restart, not an MCU reboot or a counter reset.

Before each lease the APP also finishes the whole native keyboard transaction,
including its16ms select/read gap, then observes physical idle for500us. A
logical transaction is not complete merely because the hardware wires are idle.
The APP reads ELF/DWARF-pinned pending/phase fields and calls normal service
until both are zero, with a100ms cap. No service submits another keyboard job
until the transfer and restoration are complete.

Read-only snapshots cover native timeout/reset/abort/keyboard errors, worker
stage/result, keyboard pending/phase/online, GPIO levels and passive I2C status.
They bracket the first delta at before/inside/after logical fence, after physical
fence, after restoration, after service/key polling, module load and cleanup.
Snapshots are sequential across cores, not atomic captures of a bus edge.

M3 restoration retains the verified open-drain START/STOP recovery followed by
I2C1 SWRST and address/timing/control restore from ST ES096 section2.8.7.
TIM1/2/3 and PMU I2C2 configuration are not changed. The M3 identity module
calculates the known BIOS CRC in cooperative128-byte steps and requires the
stock clocks, Cortex-M3 CPUID and64KiB factory Flash size. A zero DBGMCU ID is
allowed only with those other checks, per ST ES096 section2.2.2.

## Transport variants

| Mode | Physical lines | Transfer engine |
| --- | --- | --- |
| UART reference | PC10→GP9 | Resident UART DMA |
| Two-wire clocked | PB8→GP7 clock, PB9→GP6 data | Software or TIM4_UP/DMA1ch7→GPIOB_BSRR |
| Four-wire clocked | PB9→GP6 clock, PB8/PC11/PC10→GP7/8/9 data | Three bits per software clock |
| Four-wire NRZ | PB9/PB8/PC11/PC10→GP6/7/8/9 data | TIM4_UP/ch7 and TIM4_CC3/ch5, PIO receiver and RX DMA |

NRZ4 uses common start0, eight MSB-first four-bit payload symbols and common
stop15:32 payload bits per10 symbol periods. It is asynchronous start/stop
framing, not unframed self-clocking NRZ. PIO samples at8 ticks per symbol,
autopushes32 payload bits, then pushes the stop nibble. The receiver checks every
stop nibble plus bytes/CRC and halts after the declared frame count. Precomputed
PIO divisors avoid runtime division while configuring the receiver.

M3's timer update and compare events are one72MHz timer tick apart, writing
the two GPIO ports through separate DMA channels. An idle tail keeps the last
stop symbol stable before restoring the pins. No per-symbol CPU servicing or
global IRQ masking is used. The experiment checks both DMA channels and refuses
other enabled request sources sharing channel5, including PMU I2C2 DMA.

Run015 exposed a restoration-order bug: writing CCR3 after restoring SR could
leave CC3IF set. The corrected code restores SR last. It acknowledges exactly
one known inherited CC3IF=8 at first acquire only when TIM4 is stopped/unclocked
and its configuration/DMA are otherwise pristine; it reports that cleanup and
rejects later dirty state. Hardware016 observed that initial8, then zero before
all later NRZ jobs. HOST regression reintroduces8 after the first job and requires
refusal, rather than hiding repeated resource faults.

The M3 burst limit is1ms and runtime slice limit2ms, with interrupts enabled.
These detect overruns; they do not promise execution time under arbitrary IRQ
load. The fixture starts after a500us readiness guard, returns Pico's pins by
2500us and defers the M3 UART result until4000us. `total_us` includes those guards
and must not be presented as production audio latency. Independent arithmetic
counters show available execution while DMA runs, not CPU utilization or power.

## Reproducing HOST checks

Controller policy needs only Python3 and checked-in synthetic status/APP
fixtures; it does not import archived hardware controllers or open a device:

```sh
python3 research/picocalc-fastlink-20261111/controller_test.py
```

ARM checks require ARM GCC14.2.1 with GDB/objcopy, Unicorn2.1.4, Pico SDK commit
`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`, and the exact archived resident ELF
plus manifest for the installed C99DE0AF/528F4874. Its ELF SHA256 is
`4139bcb17c802288c93c2ab6efa5248f996166874ffb0b2b7bf20f8a18c88bb0`.
Historical7C38C634/8A17554E is also supported with exact ELF SHA256
`75ef19a5237b0ed25357424e1fd31da2aa64c69fa98683b4300dc7f553ffce16`.
A different build from current main is not a substitute for this firmware-specific
input. Supply paths with `--resident`, `--toolchain`, `--pico-sdk` to build.py;
defaults refer to this local session. Use a Python environment with Unicorn for
the ARM scripts. Sandboxed macOS may require the normal approved execution route
for the repository's Unicorn prerequisite check.

Use fresh output directories; do not overwrite a reviewed historical kit:

```sh
python3 research/picocalc-fastlink-20261111/build.py --output .build/fastlink/reference
python3 research/picocalc-fastlink-20261111/host_test.py --kit .build/fastlink/reference
python3 research/picocalc-fastlink-20261111/build.py --nrz4 --output .build/fastlink/nrz
python3 research/picocalc-fastlink-20261111/host_test.py --kit .build/fastlink/nrz --sender-kit .build/fastlink/reference
python3 research/picocalc-fastlink-20261111/host_nrz4.py --kit .build/fastlink/nrz
python3 research/picocalc-fastlink-20261111/controller_test.py --output .build/fastlink/nrz/controller-test.json
python3 research/picocalc-fastlink-20261111/build.py --nrz4 --reference-packer --output .build/fastlink/nrz-reference
python3 research/picocalc-fastlink-20261111/host_pack.py --kit .build/fastlink/nrz --reference-kit .build/fastlink/nrz-reference
```

`--sender-kit` tests the new APP's common Pico guards/restoration using a freshly
built clocked reference sender; it explicitly writes `host-shared-test.json`.
`host_nrz4.py` tests the actual new NRZ sender, executes the actual Pico configure
function and sealed resident SDK, and writes canonical `host-test.json` bound to
both new payload hashes. Its PIO instruction model checks phase, lane skew and
clock error; those modeled timings are not physical measurements.

Current NRZ HOST coverage:105 actual ARM sender cases,15 actual Pico configuration
cases,1890 independent PIO cases,14 injected faults, seven invalid inputs, seven
consecutive jobs and one-time startup-cleanup/repeated-dirty-state regression.
Shared checks include identity/PIO/physical/logical guards,29 exact resident SDK
allocator cases, native fault latching and five Pico restoration/failure cases.
Controller checks cover11 admissions,14 authorizations,12 native frames and three
faulted cleanup workflows. The controller suite also passes with all `.build`
reads and CDC device opens denied by a Python audit hook.

`host_pack.py` executes the actual relocated optimized ARM packer on760 inputs,
checks every possible byte value, all valid block lengths, unchanged unused wave
entries, guard words and callee-saved registers. Eight full ARM INIT comparisons
check both modules against an independent encoder.96-byte INIT instruction
counts fall8910→3523; instruction counts are not physical cycles or timing.

The legacy failing M3 restoration fixture is compiled from
`fixtures/legacy_module.c`; it is not embedded/uploaded. Its package SHA256 stays
`245d2f7d09004d9977d0b14b99e39f84513bea440bad1a52e1ae5da231e8a84a`.
No historical binary or CDC log is needed for HOST regression. Identity tests use
the already tracked firmware/picocalc-m3-boot BIOS files. The diagnostic M3 HAL
field addresses are tied to that exact BIOS body and short-enum ABI, read-only.

## Session-specific hardware control

The HIL scripts retain this session's exact native firmware/UID/boot/crash
admission, archived local current_hil/device_guard backend and continuous shared
lease. They do not manufacture those prerequisites on a clean checkout. The
current default SD scope is /FLTEST017; `--session 017a`, `017b` and `018` select
separate proofs and temporary folders, with `--kit` selecting their exact APP.
Only a new byte-verified owned APP is removed.
Changed files and foreign foregrounds are preserved. cleanup.py records an older
/FLTEST14 cleanup-only procedure and is not the controller for a new run.

Preparation is HOST-only. Execution requires a fresh exact-hash one-shot grant,
finite start/finish deadlines, native admission and an exclusive root lease.
The user's direct request is honestly recorded as USER_EXPLICIT_HARDWARE_GO,
not described as coordinator approval; its request/thread/clock/no-Flash scope
must match the pinned proof. NRZ preparation also requires the completed long
I2C qualification receipt. Source, configuration and payload hashes are checked
before access. The first failed case or native delta ends the run; only resource
restoration, draining an already pending reply, UNLOAD/HELLO and owned-file/UI/
CDC/termios/lease cleanup follow. No Flash/ROM-mode/MCU-reset/crash-clear action
exists in these controllers. Old receipts and grants are never relabeled/reused.

Primary references: [RPi PIO UART receiver](https://github.com/raspberrypi/pico-examples/blob/master/pio/uart_rx/uart_rx.pio),
[ST RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f103xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf),
[ST ES096](https://www.st.com/resource/en/errata_sheet/cd00190234-stm32f101x8-b-stm32f102x8-b-and-stm32f103x8-b-medium-density-device-limitations-stmicroelectronics.pdf).
