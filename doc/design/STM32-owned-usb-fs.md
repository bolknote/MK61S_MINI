# Fixed Full Speed USB for STM32F401/F411

This sixth phase removes the last five externally compiled USB/LL sources.
All C/C++/assembly compilation inputs are now versioned in this repository;
no libgcc, libm, libstdc++, libc_nano/libc or libnosys archive member is linked.
The pinned SDK still supplies CMSIS device/core and ST interface/LL headers.
Several owned drivers and runtime routines are derived from ST or GCC code;
their attribution and license exceptions remain explicit.

| Board | Flash before | Flash after | Static RAM before | Static RAM after | CRC |
|---|---:|---:|---:|---:|---|
| Classic V3 UC1609 | 360920 | 360148 | 28464 | 28056 | ECCFCADC |
| mini V3 LCD1602 A00 | 333408 | 332616 | 27128 | 26728 | 9F241897 |

The phase saves **772/792 bytes Flash and 408/400 bytes static RAM** on
Classic/mini. From the six-phase baseline `0c0732707`, the cumulative savings
are **7660/6592 Flash bytes and 552/496 static RAM bytes**. These comparisons
use the same LIBM test profiles and feature switches. Earlier GPIO/SPI/ADC/
RTC and standalone-I/O savings precede that baseline and are not added again.
The retained heap buffers and stack budget are unchanged.

## Implementation

- `stm32f4_usb_ll.c`: OTG_FS registers, the embedded PHY and four endpoint
  numbers, fixed Full Speed, no host/HS/ULPI/DMA/isochronous branches. Reset and
  FIFO waits remain bounded; the 84/96-MHz turnaround setting is fixed at 6.
  The production bridge still validates endpoint number, packet capacity and
  buffer bounds, drains excess FIFO input, and preserves interrupt ordering.
- `stm32f4_usbd_core.c` and `stm32f4_usbd_ioreq.c`: one mutually exclusive
  CDC/MSC class, EP0 enumeration and setup/data/status sequencing. Multi-packet
  continuation, required ZLPs, class callbacks, reset and repeated suspend/
  resume remain. Interface routing follows the actual CDC/MSC descriptor;
  endpoint routing requires an opened endpoint within 0..3. The core keeps
  its no-LTO boundary for the USB power wrappers.
- `stm32f4_usbd_desc.c`: the same VID/PID, product/configuration/interface
  strings and legacy STM32 UID serial encoding. Immutable device, language,
  descriptor callback, CDC/MSC class and CDC-interface tables live in Flash.
  One 64-byte string scratch area replaces 256 bytes plus the separate serial
  scratch. Fixed text lengths are checked at compile time. String conversion
  now bounds the copy itself, including oversized input, rather than merely
  clamping the advertised descriptor length.
- `stm32f4_cdc_queue.c`: the pinned SPSC algorithm, specialized and asserted
  for 128-byte TX, 192-byte RX and 64-byte packets. RX keeps its full-packet
  reservation, gap byte and write-before-length snapshots. The 192-byte RX
  ring is not treated as a power of two. Full RX still produces NAK and the
  foreground reader rearms it without losing bytes.

The low-level and core files retain ST-derived register/protocol sequences
under the included USB LL/middleware licenses. The descriptor source retains
its original SLA0044 notice and queue source its full BSD notice. Legacy
Arduino builds retain their external descriptor symbols and mutable class
API declarations; all newly owned replacement sources are native-only.

## Qualification

All 16 F411 and nine F401 product/capability variants build. Source and archive
gates pass on those 25 plus the two installed test profiles: zero external
implementation source files and zero standard runtime archive members.
The final sealed installed binaries are byte-identical to the rebuild after
preserving the legacy preprocessor branch.

The ARM fixture compiles the actual core, I/O, request parser, descriptors,
queues and memory functions with an independent fake wire. It checks device
and configuration enumeration, addressing/configuration, CDC/MSC interface
routing, malformed endpoint indices, EP0 67-byte continuation, exact-64-byte
ZLP, 130-byte OUT completion, reset, suspend/resume, stable serial encoding,
oversized-string guard bytes and 50000 randomized queue rounds. It passes
with the Classic, mini and F401 production settings. Production controller
register models pass on both F411 images and F401; the production Classic
CDC model also covers ACM input bounds, ZLP completion and RX NAK/rearm.
Host power, STOP, CDC, SCSI safety, screen protocol/key and prelink suites pass.

Both installed ELFs pass 1897 high-precision math vectors plus 54 IEEE cases,
and three ordinary service APPs each run at three SRAM addresses. Their math
kernels, EABI routines, emulator source and NOR cache sizes are unchanged.

Both physical boards pass:

- 4-KiB binary MSC import/export with a Unicode filename, two safe ejections,
  two CDC returns, reset and cleanup. Minimum observed free stack is
  **12632 bytes Classic / 12544 mini**, exceeding the 12288-byte requirement.
- CDC writes/readback at 1,63,64,65,255,256,257,4095,4096 bytes.
- 103 complete framebuffer captures, including 100 requested retransmissions,
  against an independent pixel formula. The frame SHA-256 is recorded.
- Twelve ADC probes, five restored emulator batches and 100 CRC-checked
  64-KiB NOR reads each, without SPI/DMA errors or ownership imbalance.
- Exact comparison of every original file fingerprint, active program,
  registers, stack and current directory against this task's fresh snapshot.
  Temporary files are removed and RTC correction/settings are untouched.

| Board | Prior/new emulator cycles per step | Prior/new 64-KiB NOR read, us |
|---|---:|---:|
| Classic | 1712125 / 1709537 | 24988.5 / 24993 |
| mini | 1711105 / 1711024 | 24767 / 24810.5 |

NOR times are medians of 60 reads. Differences stay below 0.2%; they do not
establish an algorithmic speed improvement from the USB change.

The existing graphics HIL explicitly resets the zero/empty calculator after
closing its APP. USB Screen DETACH returns to WAITING_FOR_HOST and retains
the session/OVERLAY for reconnection; it is not a full session cancellation.
The previously reproduced storage-cleanup limitation is not claimed fixed by
this USB port. Original files and logical state are still verified exactly.

Physical Classic RTC/ESC wake against actual Mac suspend remains an operator
check pending on this final USB image. No diagnostic sleep request is armed.
No earlier image's sleep result is substituted for this image's qualification.

```sh
python3 tests/usb_fs_control_arm_self_test.py BUILD/compile_commands.json
python3 tests/stm32f4_usb_arm_self_test.py BUILD/resident.elf
python3 tests/stm32f4_cdc_arm_self_test.py CLASSIC/resident.elf
python3 tests/check_stm32_standalone_build.py BUILD/compile_commands.json
python3 tests/check_native_runtime_libraries.py BUILD/resident.map --without-libc
```

ARM runners use Unicorn with Cortex-M4 support. Detailed machine-readable
measurements: [stm32-owned-usb-fs-20261015.json](../measurements/stm32-owned-usb-fs-20261015.json).
SEGGER precision-qualified comparison remains in
[STM32-owned-eabi.md](STM32-owned-eabi.md).
