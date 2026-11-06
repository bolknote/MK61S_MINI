# PicoCalc Spectrum clock diagnostics, 2026-11-06

This checkpoint contains the exact native sources used for firmware
`C3F35FAE`, CRC `B5299177`, and the complete Cosmic Payback measurements.
The seven M0 Math files match the previously qualified overlay recorded in
`math-overlay.json`; they are included to preserve the tested baseline.

The optional build flag is off by default:

```sh
python3 tools/firmware/picocalc/build_picocalc.py --cosmic-clock-diagnostic \
  --sdk /path/to/pico-sdk --toolchain /path/to/arm-none-eabi/bin
```

The diagnostic image boots at 125 MHz and supports 130–250 MHz in 10 MHz
steps. USB and peripheral clocks stay at 48 MHz. PLL transitions happen
while the USB controller is deinitialized and held in reset; the host must
rebind the same UID after enumeration. A 105-second independent lease
returns the board to a fresh 125 MHz boot. The delayed normal reset no
longer returns to the main loop that would keep feeding its watchdog.
Pending peripheral work finishes before reset; boot clears the dedicated
keyboard I2C bus using open-drain clocks and STOP.

In this build only, the native integer-span VM kernel executes from XIP,
freeing 5904 bytes for the 49148-byte profiling APP. Full 125/200/250 MHz
runs use the same firmware, APP, snapshot, peripheral clocks, PCM rate and
PIO/PWM rates. XIP follows CPU at 31.25/50/62.5 MHz. Intermediate points
are shorter USB/native-Math checks; their rounded PIO/PWM dividers never
exceed the diagnostic clock limits.

`RESULTS.md` describes the measurements and limits. The original final
ladder receipt remains **HOLD**: its complete 250 MHz game interval and
return to 125 MHz succeeded, but the host checked for a CDC child too
early. The archived IORegistry evidence showed the USB device before the
CDC child. The corrected observer passed in `TIMEOUT-PROBE-001`: the USB
device returned after 106.694 seconds, then keyboard, display and SD were
ready. This history is retained rather than rewriting the original receipt.

The archive includes all 30 timing windows, 14 clock receipts, the timeout
receipt, 48 complete checksum transfers, and the two controller versions.
Absolute paths in as-run JSON and controller files are historical provenance.
Those controllers depend on the local frozen hardware harness; they are
not a portable device launcher or a new device-access authorization.
Firmware binaries, ROMs and game assets are represented by their hashes.

Read-only verification requires only Python's standard library:

```sh
python3 -B research/spectrum-clock-20261106/verify.py
```

Clock/reset fault injection and PCM ownership checks are also part of
`tests/run_picocalc_hardware_tests.sh`; set `MK61_TEST_SANITIZERS=1` to use
ASan/UBSan. No further hardware access is needed to verify this checkpoint.

After the tests the device was released at 125 MHz, with every CDC
descriptor closed and the three temporary SD files removed. The initial
roughly 82 ms gap between accepted video submissions remains; physical
LCD scanout and speaker latency were not measured.
