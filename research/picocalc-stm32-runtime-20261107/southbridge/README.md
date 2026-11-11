# Southbridge with downloadable STM32 modules

This is the current compiled candidate. It ports our portable S3M1 loader to
JackCarterSmith's PicoCalc Southbridge, pinned at mirror commit
`1b649c826b213b460bca7172f696ec7619d93be0`. The older stock/Arduino prototype
in the parent directory remains a reference. Neither image has been flashed.

The resident image contains the keyboard BIOS and the loader. A separately
compiled Thumb-2 module is uploaded into SRAM over USART3, executed in short
cooperative calls, and unloaded without rewriting Flash. It does not contain
MK61S, an emulator, or an embedded neural network. `q4_dot.s3m` is a 328-byte
proof module for Q4 weights × INT16 activations; group scales stay with the
caller. It demonstrates the interface, not an inference speedup.

## Memory

The generated `manifest.json` is authoritative for exact image sizes. SRAM is
20,480 bytes: 9,700 bytes of globals including the entire loader, 4,096 bytes
reserved for stack, and 6,684 bytes unallocated. The linker enforces a minimum
2,048-byte gap below the stack. There is no heap allocation. The 6,144-byte
module code+BSS limit stays in place until hardware stack measurements justify
using more memory.

The compact loader occupies 8,228 bytes:

| Allocation | Bytes |
|---|---:|
| Module/package arena | 6,464 |
| Job input and output | 1,024 |
| RX framing + cached reply | 544 |
| Backend, validation and state | 196 |

UART uses another 512-byte DMA RX ring and small counters. COBS decoding shares
its input buffer; TX DMA reads the cached reply directly. These remove 544 bytes
of duplication compared with the stock-based prototype. A reply remains pinned
until DMA finishes, including while a module advances between keyboard polls.

Flash is limited to 62 KiB for code plus the upstream 2 KiB settings area.
Modules do not have a Flash-write command. Southbridge settings keep their own
last-two-page allocation; code upload cannot consume it. Settings writes are
deferred whenever a module is resident or the UART exchange is active.

## Clock, UART and normal keyboard functions

Active clock is 72 MHz from HSE8 × PLL9; APB1 is 36 MHz and APB2 is 72 MHz.
USART3 uses partial remap PC10 TX / PC11 RX, wired to Pico GP9 RX / GP8 TX.
BRR=16 gives nominal 2,250,000 baud, 8N1: at most 225,000 bytes/s per direction
before framing and acknowledgement. DMA1 Channel3 receives into the ring;
Channel2 transmits replies. Physical speed and Pico-side divider error are
not yet measured. UART1 through the mainboard USB-C/CH340 is the separate ROM
programming/debug route.

TIM2 is reconfigured to PSC=71, ARR=999 for the exact 1 ms time base and a 1 MHz
counter used for call timing. TIM1 and TIM3 use PSC=17, preserving Southbridge's
backlight PWM frequencies when moving from 4 MHz to 72 MHz. The keyboard matrix,
FIFO, PMU, battery and RTC implementation remain Southbridge's. A module gets
at most one call per main-loop turn; keyboard processing runs between turns.

The I²C address stays 0x1F. The stock Pico driver's used registers are preserved:
FIFO 0x09 returns `{state,key}`; battery 0x0B returns `{register,value}`;
LCD 0x05 and keyboard light 0x0A accept and echo raw 0..255 brightness. Raw byte
brightness replaces Southbridge's step indices, including wake restoration and
keyboard shortcuts. Settings use a distinct format marker; RTC backup markers
are unchanged. The community BIOS's extended configuration/reset/RTC register
semantics otherwise remain its own, not a complete stock-register emulation.

Power-off/reset first stops DMA and floats the UART pins, then removes Pico
power and clears the module without executing its FINI. On power-up UART starts
after the power GPIOs are enabled. A fresh module upload is required afterward.
Automatic option-byte programming was removed. Sleep uses STOP if existing
option bytes permit waking without reset; otherwise it falls back to SLEEP,
which consumes more idle power. Neither power consumption nor wake behavior
has been validated on the board yet.

Native modules are trusted cooperative code. Validation checks package sizes,
CRC, ABI, target and relocations. Slice overrun is detected after the call
returns; an infinite loop or invalid native memory access can still hang the
keyboard controller. This version does not promise preemption or isolation.

## Reproduction and tests

From the repository root:

```sh
python3 research/picocalc-stm32-runtime-20261107/southbridge/build.py
python3 research/picocalc-stm32-runtime-20261107/southbridge/verify.py
tmp/urq/venv/bin/python dev/tools/run_arm_test.py research/picocalc-stm32-runtime-20261107/southbridge/tests/arm_execution.py
tmp/urq/venv/bin/python dev/tools/run_arm_test.py research/picocalc-stm32-runtime-20261107/southbridge/tests/uart_dma_execution.py
tmp/urq/venv/bin/python dev/tools/run_arm_test.py research/picocalc-stm32-runtime-20261107/southbridge/tests/combined_execution.py
python3 research/picocalc-stm32-runtime-20261107/southbridge/review.py
```

The compiler path and pinned source/submodule paths are checked by `build.py`.
The required upstream tree lives in `.build/stm32-module-runtime-20261107/community-southbridge`;
it and the original size-comparison builds are left unmodified. Staging and
outputs go to `.build/stm32-module-runtime-20261107/southbridge-runtime`.
On macOS, the repository Unicorn launcher may require normal tool approval for
`hw.cachelinesize`; it stops before constructing an emulator if unavailable.

Checks include ASan/UBSan, 1,360 independent int64 row references, 11 malformed
packages, framing noise, 804 in-place COBS vectors and 253 overlapping READ
lengths. The compact ARM loader executes the actual relocated module, with
309 rows over 40 jobs, replay and cancellation checks. A separate MMIO model
tests the DMA driver, wrap/overrun/fault recovery, and GPIO ownership. The
combined ARM model exercises the real bridge, wire protocol, I²C callbacks,
FIFO, backlight implementation, clock function, timing snapshots and sleep
policy. Modeled timing/stack use are not hardware measurements.

The test module remains separate from the resident firmware. Source gates
exclude MK61S product files and option-byte programming. No device is opened
by these build and test commands. Firmware artifacts, hashes and finite test
reports are listed in `review-packet.json` under the output directory.

## Hardware step still pending

No STM32 write, option-byte change, Pico image replacement or model benchmark
was performed by this port. Board USB-C is CH340 `/dev/cu.usbserial-1120`; Pico
CDC is `/dev/cu.usbmodem11301`. Ports must be re-identified before use.

ROM access requires physical DIP1 ON and a board power cycle. First query the
ROM chip ID through the mainboard port. Only after that matches the F103 target
use the exact reviewed binary and bounded page count with write verification;
do not mass-erase, change protection/options, run GO/reset automatically, or
save/restore old firmware/calculator state. Return DIP1 OFF and power-cycle
afterward. Keyboard, power, UART throughput/errors and stack watermark need
physical regression tests; a Pico-side runtime client is the next integration
step. The M0 fixture and current Pico image are outside this change.

Southbridge upstream is LGPL-3.0; the staged tree retains its LICENSE and the
pinned STM32 driver licenses. Original source is available from the author's
project and its declared GitHub mirror. The reproducible source/patch build
is retained alongside this firmware.
