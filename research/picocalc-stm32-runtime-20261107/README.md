# STM32F103 native module runtime: first compiled prototype

**Current implementation:** the smaller HAL-based Southbridge port has been
flashed and physically tested. See [hardware results](HARDWARE_RESULTS.md) for
UART/module operation, DWT kernel counts and measured transport capacity.
The [Southbridge build note](southbridge/README.md) is the frozen pre-flash
snapshot. This stock/Arduino prototype remains an unflashed compiled reference.

This is an isolated extension of the **stock PicoCalc keyboard firmware**, not
MK61S running on the keyboard controller. It has not been flashed to STM32.
The main MK61S/Pico firmware, its model experiments and the M0 benchmark fixture
are independent and were not changed.

## Built and checked

- Resident image: STM32F103R8T6 / Cortex-M3,64KiB Flash,20KiB SRAM.
- Compiled firmware occupies37,808B Flash; globals occupy11,692B, plus1,536B
  linker heap/stack reserve and4B alignment, leaving7,248B beyond it.
- Runtime's fixed allocation is8,500B. Its executable image+BSS limit is6,144B;
  input and output buffers are512B each. Code executes from SRAM.
- The independently compiled `q4_dot.s3m` package is328B:260B code/data,
  4B BSS, one absolute relocation, and its header/relocation table. It is **not
  embedded in resident firmware**.
- HOST ASan/UBSan:160 jobs /1,360 independent int64 row references;11 malformed
  packages; cancellation, timeout and returned-slice overrun;60,000 noise bytes.
- ARM emulator: actual relocated Thumb-2 instructions executed from SRAM;
  309 reference rows, repeated START idempotence, cancellation, BSS reset on
  reload, bad-package rejection, stack and callee-saved registers checked.
- ARM register-model test checks USART3/DMA configuration, pending-wrap
  accounting, overrun/error detection, TX buffer lifetime and unrelated
  GPIO/I2C clock bits. This is **not a physical UART speed or keyboard test**.

Artifacts live in `.build/stm32-module-runtime-20261107/`:

- `firmware/picocalc_keyboard.ino.bin`, `.elf`, `.hex`, `manifest.json`
- `module/q4_dot.s3m`, `.elf`, `manifest.json`
- `host-verification.json`, `arm-execution.json`, `uart-dma-execution.json`
- `pico-admission.json`: one read-only admission on allocated PicoCalc;
  F0E86C32/5009F89E BOOT2, CLOSED/NONE, APPbuffers0 and error counters0.

No target timing, throughput, keyboard responsiveness or installed runtime is
claimed. No target firmware, clock or reset was changed in that admission.

## Stock keyboard preservation

`upstream.json` pins official source commit
`fdcfe2c87a56b6dbcd540e91de1161d483872af9`. The files in
`vendor/picocalc_keyboard/` are unmodified copies. The generated sketch adds:

1. two bridge declarations;
2. `coproc_setup()` after normal keyboard/PMU initialization;
3. `coproc_poll()` inside the original busy wait, preserving its10ms interval.

The key matrix, FIFO, I2C callbacks/register protocol, battery, backlight and
power-management code are copied unchanged. The source gate checks their hashes
and verifies that none of the MK61S product `code/` or `ports/` sources enter
this firmware. This source check does not replace physical regression tests.

## UART and ownership

The resident keyboard firmware owns USART3, PC10 TX / PC11 RX, partial remap.
Pico GP8 TX connects to STM32 RX and GP9 RX to STM32 TX on the v2 schematic.
PMU I2C2 on PB10/PB11 and PC12 headphone detection retain their pins.

At APB1=36MHz, BRR=16 selects the specified USART3 maximum **2,250,000 baud**.
8N1 carries8 data bits without parity plus one start and one stop bit: an ideal
225,000 bytes/s per direction before framing and acknowledgements. Different
APB1 clocks are refused. The physical Pico UART divisor and error rate remain
unmeasured.

RX: DMA1 Channel3,512-byte circular buffer, one IRQ per full ring rather than
one per byte. TX: DMA1 Channel2, up to272 bytes per response packet. Busy DMA
channels are refused. The old UART1 debug path stays in the stock firmware.
Modules use RAM job buffers; they do not own the UART/peripheral.

A module is cooperative: one bounded `STEP` per polling iteration, with keyboard
and PMU work remaining in their original loop. Slice limits are checked **after
return**. This is not preemptive isolation: a buggy native module can hang or
corrupt firmware. This first version is for our audited modules. The sample
executes32 MACs per step and has no peripheral access.

## Module/package ABI1

`include/stm3_module.h` defines a64-byte little-endian S3M1 header: target/ABI,
image+BSS sizes, Thumb entry offset, input/output/stack/slice limits, and separate
header/payload CRC32. Absolute relocation offsets follow the image. The loader
checks all bounds and relocation targets before moving/patching code and
zeroing BSS. There is no ELF parser or heap allocation on STM32.

Programs are linked at0x20000000 with word relocations and packaged on the
computer. The loader adjusts them to its actual SRAM slot. The module entry is
`entry(INIT/STEP/CANCEL/FINI, api, job)`. The API supplies a clock; the job supplies
input/output pointers and progress. No runtime-specific UART code is necessary
inside a program.

`q4_dot.c` is the integer dot-product part of a quantized matmul, **without**
per-group floating-point scales. Input: magic QDT1,u32 rows1..16,u32 columns32,
32 little-endian int16 activations, then16 packed Q4 bytes per row (nibble minus8).
Output: u32 rows,u32 persistent run counter, then one int32 dot per row. Every
row is computed in its own STEP; parameters and output are512B bounded buffers.

## Wire protocol1

COBS frame plus zero delimiter. A leading zero is allowed for resynchronization.
Decoded request: version:u8, operation:u8, sequence:u16, payload_bytes:u16,
flags:u16(0), payload(up to256B), CRC32(header+payload). Response echoes sequence,
sets operation bit7 and starts its payload with a u32 status code.

One outstanding request is allowed. An identical replay of the last sequence
returns the cached response without executing START/WRITE again. Reusing that
sequence for different contents is dropped and counted. Corrupt frames are
counted and discarded. UART overruns discard the partial frame.

Commands: HELLO, LOAD_BEGIN, LOAD_CHUNK, LOAD_COMMIT, WRITE, START, STATUS, READ,
CANCEL_JOB, UNLOAD. Constants and BSS persist between jobs in one loaded module.
LOAD is refused while a module is resident; UNLOAD is refused during a job.
Cancellation takes effect between steps. Failed loads cannot execute stale code.
There is no Flash-writing command in this runtime.

## Rebuild on this workspace

Prerequisites are the installed STM32 Arduino core2.12.0 / CMSIS6.2.0 / GCC14.2.1,
plus XPowersLib at commit4744c7e6a5fc57e72996dbae0cd3b1a7e5299bb6 in the experiment's
`.build/.../XPowersLib` directory. The exact external sources are pinned in
`upstream.json`. New source uses the repository GPLv3 license; upstream sources
retain their authorship, and XPowersLib retains its MIT license.

```sh
python3 research/picocalc-stm32-runtime-20261107/tools/build.py --firmware
python3 research/picocalc-stm32-runtime-20261107/tools/verify_host.py
tmp/urq/venv/bin/python dev/tools/run_arm_test.py research/picocalc-stm32-runtime-20261107/tests/arm_execution.py
tmp/urq/venv/bin/python dev/tools/run_arm_test.py research/picocalc-stm32-runtime-20261107/tests/uart_dma_execution.py
```

On this Mac, Unicorn needs normal tool approval outside the sandbox because its
safe preflight cannot query hw.cachelinesize inside the sandbox. The unchanged
repository guard stops before constructing the emulator if that query fails.

## Hardware route, not yet executed

The manufacturer's documented keyboard-flashing route is USB-C on the mainboard,
DIP1 ON and STM32's USART1 ROM loader; DIP1 OFF and power cycle return to the
keyboard firmware. Runtime traffic to/from Pico uses USART3 instead. The ROM
programming protocol's serial settings are separate from runtime2.25Mbaud.

The USB-UART appeared as `/dev/cu.usbserial-1120` after the user connected it;
ROM chip ID and boot mode have not been queried. No STM32 erase/write, old
firmware readback or user-state backup has occurred. Do not use the RP2040
BOOTSEL/picotool path to program this STM32 image.

## Community BIOS investigation

Closest alternative: JackCarterSmith's PicoCalc Southbridge, inspected through
public mirror `shtirlic/picocalc_southbridge` commit
`1b649c826b213b460bca7172f696ec7619d93be0`. Its README reports a ~25KB HAL firmware
with RTC, power saving and persistent settings. Core sources have no native
module/package loader. Optional USART3 initialization is present at115200 baud;
there is no corresponding LOAD/RUN program protocol in the inspected Core tree.
Some existing register meanings change, including backlight0..9 and reset/power
control; I2C compatibility must be tested before adopting it as a replacement.
The primary hosting site denied browser access; the mirror may lag upstream.

The community's2025 wishlist explicitly discusses transmitting programs into
STM32 and running them concurrently, but presents it as a proposed feature.
Our runtime is portable C, with separate Arduino bridge and F103 DMA driver,
so it can be evaluated on that HAL base later without changing module ABI.

References:
- https://github.com/clockworkpi/PicoCalc/wiki/Setting-Up-Arduino-Development-for-PicoCalc-keyboard
- https://github.com/shtirlic/picocalc_southbridge
- https://forum.clockworkpi.com/t/keyboard-bios-feature-bugfix-wishlist/18497
