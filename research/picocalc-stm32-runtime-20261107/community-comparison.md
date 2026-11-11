# Keyboard BIOS size comparison,2026-11-07

All builds use xPack ARM GCC14.2.1, Cortex-M3 Thumb soft ABI. These are compiled
resource measurements only; no target firmware was programmed and no power,
latency or UART throughput was measured. Southbridge mirror commit is
1b649c826b213b460bca7172f696ec7619d93be0; stock commit isfdcfe2c87a56b6dbcd540e91de1161d483872af9. Exact pinned
submodule versions and artifact hashes are in `.build/stm32-module-runtime-20261107/bios-comparison.json`.

| Firmware | Optimization | Flash load bytes | Global SRAM data+BSS | Linker heap/stack reserve,alignment included |
|---|---|---:|---:|---:|
| Stock keyboard v1.6 | -Os -flto | 34176 | 2380 | 1540 |
| Southbridge default | -O3 | 36252 | 952 | 1536 |
| Southbridge size build | -Os -flto | 22380 | 928 | 1536 |
| Stock+our module runtime/DMA | -Os -flto | 37808 | 11692 | 1540 |

Compare the first and third rows to evaluate the two bare keyboard bases under
the same optimization choice. The fourth includes the8,500-byte runtime and
DMA buffers and must not be compared against a bare Southbridge as equivalent
functionality. The clock settings and feature sets also differ.

The size-tuned Southbridge saves11,796 Flash bytes(34.5%) and1,452 global SRAM
bytes against the stock base. Its linker reserves2KiB Flash for EEPROM/settings,
so the increase in free code/constant Flash is9,748 bytes after that reservation.
The default-O3 Southbridge is actually2,076 bytes larger in Flash than our
stock-Os/LTO baseline; compactness requires appropriate build settings.

Southbridge uses HAL/CMSIS directly, has RTC/power-saving/settings features and
smaller driver state. The inspected default clock is4MHz(HSE8MHz, AHB/2),
not72MHz. That helps idle power but is not a fast neural-compute profile. Our
2.25Mbaud driver intentionally refuses APB1 other than36MHz, so a port needs
a deliberate72MHz compute clock profile, peripheral/timebase changes, and
keyboard/I2C regression checks. Power figures in the upstream README are not
measurements of our build or of72MHz compute.

The mirror has changed backlight/reset/power register semantics and no LOAD/RUN
module service. Our runtime is portable C and can be integrated after auditing
those interfaces. Existing keyboard code would remain resident. More free
Flash/SRAM does not change the physical20KiB RAM limit or add DSP/FPU hardware.

Reproduction(first initialize the three pinned upstream submodules):

```sh
make -C .build/stm32-module-runtime-20261107/community-southbridge -j4 GCC_PATH=/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin BUILD_DIR=build-default
make -C .build/stm32-module-runtime-20261107/community-southbridge -j4 GCC_PATH=/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin BUILD_DIR=build-size OPT='-Os -flto'
python3 research/picocalc-stm32-runtime-20261107/tools/compare_bios.py
```

Sources:
- https://github.com/shtirlic/picocalc_southbridge
- Core/Src/hal_interface.c:SystemClock_Config
- STM32F103XX_FLASH.ld:62KiB code Flash+2KiB FEE,20KiB SRAM
