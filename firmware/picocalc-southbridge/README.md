# PicoCalc Southbridge firmware

Combined STM32F103R8 image: I²C recovery, Spectrum deferred completion, and AXP2101 power telemetry. SHA256: `3b313836c5fa260851c4a8cc6dc4bca8b3c98b7270cc9e484932cd7f268e7282`.

This directory retains the historical source baseline used by the [async PMU build recipe](../../ports/picocalc/bios/README.md#неблокирующий-вариант-pmu). Its blocking PMU reader timed out on the device. On 2026-11-08 the async image `640d7621ed47547f09a6df1312e99d1c95e06cce28aaca1cfeb252396b9b16d8` was installed and readback-verified; initial hardware checks reported valid battery and external-power telemetry. Build that variant for the PMU fix. The baseline BIN and archive here are unchanged so existing recipes and evidence remain reproducible. See the [hardware results and limitations](../../doc/measurements/picocalc-pmu-async-20261108.json).

The power register is read-only: register `0x0F` returns `{0x0F, 0xA0 | flags}`. Flags: VALID `0x10`, charge complete `0x08`, charging `0x04`, external supply `0x02`, battery present `0x01`. Invalid telemetry is exactly `0xA0`. Pico HUD support is a separate Pico firmware change.

`source.zip` contains the complete staged Core, Makefile, linker/startup files, upstream license, exact staging and verification recipes, and test evidence. Every archive entry is hashed in `manifest.json`. There are no saved device settings or previous device firmware images.

To rebuild, extract the archive into an empty directory. Check out the pinned Southbridge fork `https://github.com/shtirlic/picocalc_southbridge.git` at the commits listed in `upstream-pins.json`, including its Driver submodules. Set `STM32_DRIVERS` to that checkout's absolute `Drivers` path and `ARM_GCC_BIN` to the xPack GNU Arm Embedded GCC 14.2.1-1.1 `bin` directory, then run `bash rebuild.sh`. The script checks the resulting binary SHA256.

ROM programming requires a fresh chip ID check (`0x410`) and DIP1 ON with a board power cycle. Program at `0x08000000`, erase only pages 0–26 (27 KiB), and verify. Settings at `0x0800F800..0x08010000` are outside the erase range. The reviewed plan makes no option/protection writes or automatic GO/reset. Return DIP1 to OFF and power-cycle before validating keyboard, UART and power telemetry.

HOST/ARM checks passed for this baseline. Its original physical I²C/PMU failure evidence remains a HOLD; the successful async-image checks linked above apply to a different BIN.
