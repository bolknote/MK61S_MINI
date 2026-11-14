# PicoCalc: Battery/Keyboard before the NRZ4 game test

2026-11-11. This report records HOST validation. It is not an NRZ4 electrical,
throughput, or game-audio qualification.

Pico A1A8DBA6 / CRC 9A333968 and M3 B89B1FE5 were installed and read back.
The first short-test attempt stopped during SD staging, before the first game:
BATTERY_ERRORS rose from 0 to 1; I2C timeout/abort/reset and keyboard error
counters stayed at zero. The original HOLD receipt and raw CDC capture remain
in `.build/spectrum-nrz4-audio-20261111/nrz-hardware-short-001/`.
The offending register/value bytes were not captured by that firmware.

Two independent native defects were reproduced on the HOST:

- The M3 asynchronous PMU implementation publishes legacy BAT=0x7F, or 0xFF
  with the charging flag, for an unknown percentage. The old native decoder
  rejected these valid values.
- M3 expires an unconsumed register selection after one second. Core0 can be
  inside an SD operation that feeds the watchdog, so the next actual
  `Keyboard::poll` read can receive 0,0 without a physical I2C error. The
  archived actual polling body reproduces this after a 1.2-second pause.

Neither reproduction establishes which caused the observed single error.
The candidate accepts documented UNKNOWN, counts these observations separately,
and renews a pending selection at age >=900 ms before issuing a read. This
covers keyboard FIFO, battery, version discovery and power status. A completed
buffered key is consumed without renewal. Malformed replies and failed transfers
still count as errors. The first fault is retained with phase, selected register,
raw register/value, transfer count, timestamp and selection age.

Validation passed:

- Actual source polling with ASan/UBSan: reference failure, all register phases,
  renewal boundary, busy admission, buffered key, valid UNKNOWN and malformed
  percentages.
- Actual sealed ARM instructions: 18 cases, including timestamp rollover and
  exact first-fault fields; modeled I2C peer and timer.
- Actual NRZ4 Pico ARM regression: seven normal transfers, eleven fault cases,
  ten admission cases and ten service-cleanup cases; modeled peripherals.
- Full platform suite with `MK61_TEST_SANITIZERS=1`.
- The finite HIL controller in memory: Pico-only install and readback/startup/
  retained-crash failures, no automatic replay, first-fault stop, owned-file
  cleanup, raw startup observations, two ready snapshots, and long-test gate.

Candidate Pico E9EB41B5 / CRC A60BB421 is 1,793,244 bytes; static SRAM is
120,484 bytes and foreground heap is 108,892 bytes. Cold C5 diagnostics occupy
357 bytes at 0x1014D000 in the existing Flash gap; math/AI slots and the retained
crash address are unchanged. M3 B89B1FE5 is unchanged, at 72 MHz. The intended
Pico test clock is 125 MHz.

Package 006 pins the complete production compilation source fingerprint,
firmware, ELF, ARM reports, probes and controller. Scope: Pico firmware sectors
only, one planned normal Pico reboot, no M3 write/restart, and no settings,
ROM-cache, production SD or game changes. The new short002 run records battery
telemetry after each staged file and each game. Any real error stops the run.
Four same-package strict short PASS results are required before a 30,000-frame
long test. Hardware results, when available, must be recorded separately from
these HOST results.

## Hardware follow-up

The approved E9EB41B5 / A60BB421 image was subsequently installed; its full BIN
readback matched. Fresh read-only admission003 passed on boot22, including the
retained crash comparison, two complete C5 reports, SD/PSRAM readiness and zero
native error counters. The first startup capture was an incomplete unsolicited
report, and an independent controller receipt-serialization defect was corrected;
the original failed attempts remain preserved rather than relabeled PASS.

short002 staged all ten owned files without battery, keyboard or I2C errors.
AYABC then stopped after four measured game frames: 18 NRZ blocks / 2,124 audio
frames were delivered. M3_ERROR=-46 means the stop-nibble decoder accepted the
capture but the following frame validator rejected it. Without the raw block it
cannot distinguish magic, sequence, length, status, CRC or padding failure.
The 20,056 us maximum hold includes bounded recovery after the fault; it is not
evidence of a 20 ms M3 computation or late response.

Other maxima: I2C lease wait 5,154 us, reported transport 1,066 us, restoration
165 us; startup priming 22,951 us. These are maxima from different observations,
not an additive timeline of one block. Successful block times were 3,338–3,838 us;
M3 profile maximum job/slice was 1,864/1,489 us. The failed-frame interval reached
40,291 us and game lag 19,881 us. The run is HOLD. The other three cases and long
test were not run. Owned files were removed; APP, M3/SDK, CDC and root lease were
released with battery and I2C counters unchanged.

A separate SD-only diagnostic APP is prepared to copy the first already published
fault before Core0 can destroy Context, with exact ELF/DWARF and immutable Flash
identity guards. It does not read freed memory; missing a capture is explicit.
Its actual relocated ARM tests passed nine cases with all writes restricted to
APP/stack, including exact 744-byte snapshot/hex round-trip. The default probe
without the observer rebuilt byte-for-byte identically. This diagnostic is not a
strict qualification result and requires no new firmware image.
