# Fixed Full Speed EP0 requests

The native CDC/MSC device has one active class, configuration 1 and alternate
setting 0. Its standard request handler now uses these fixed contracts rather
than generic multi-class routing. Configuration replies read the registered
immutable descriptor; string getters share one checked dispatch. The device
retains its VID/PID, identity, descriptors, CDC line coding and disk protocol.
No remote wakeup is advertised; unsupported remote-wakeup and high-speed test
features now STALL. Core startup, endpoint transfer sequencing and USB power
policy are unchanged.

Request direction, recipient, complete 16-bit indices, lengths, values, active
interfaces and endpoints remain validated. Missing/failed class callbacks
STALL. Reselecting configuration 1 reinitializes endpoints, and failed Init
unwinds the class and returns to addressed/configuration 0. CLEAR_FEATURE for
MSC notifies BOT after clearing HALT and before its status ACK; CDC endpoints
have no BOT callback. Replies use persistent descriptors/device fields, never
stack locals. Compile-time assertions reject incompatible future USB profiles.

The wire expectations follow USB 2.0 chapter 9, available from
[USB-IF](https://www.usb.org/document-library/usb-20-specification). ST-derived
copyright and the repository middleware license are retained.

## Matched measurements

Both controls and candidates use base main `57835a271`, GNU Arm GCC 14.2.1,
identical source/build paths, feature flags and SOURCE_DATE_EPOCH 1791969300.
Flash includes the sealed footer. Final builds containing the profile assertions
produce the exact BINs qualified on hardware.

| Profile | Flash before → after | Saved | Static RAM |
|---|---:|---:|---:|
| Classic V3 UC1609 | 359560 → 359200 | 360 | 28072, unchanged |
| mini V3 LCD1602 A00 | 332000 → 331656 | 344 | 26728, unchanged |

Classic's 60-sample 64-KiB NOR median stays 25032 µs; mini changes 24805.5→24812 µs
(+0.026%). Core-step medians change 1712123→1709889 cycles (−0.13%) and
1708305→1711027 (+0.16%). These small measurements do not establish a CPU
speedup. Minimum ordinary MSC stack headroom is 12632/12544 bytes, above the
unchanged 12288-byte test target. The 16-KiB firmware stack/guard is unchanged.

## Tests and hardware

The Cortex-M4 fixture runs 8 suites per profile: enumeration, segmented
transfers, ZLP, reset/suspend/resume, all descriptor lengths/strings, failed and
repeated configuration, endpoint HALT/BOT recovery, invalid requests and every
16-bit endpoint/interface index. It also checks 50000 queue transitions. The
actual-controller MMIO model, 22 BOT/SCSI suites, ASan/UBSan disk/session tests,
APP RAM and source/archive gates pass.

Classic is qualified before mini. Each candidate passes 50 actual libusb EP0
requests without claiming/detaching the CDC interface: exact descriptor bytes,
statuses, interfaces, malformed requests and recovery from STALL. Ordinary MSC
then imports/exports a 4096-byte Unicode-name binary file, ejects twice, restores
CDC and verifies reset persistence. CDC boundary files cover 1, 63, 64, 65, 255, 256,
257, 4095, 4096 bytes; 100 CRC-checked NOR reads show no DMA/bus errors. All 44
Classic files/four directories and ten mini files/three directories, calculator
program/registers/stack/IP/current directory and RTC settings are preserved.
Qualified CRCs are D80CE1D1 and A2D2F970. Physical Mac sleep is not repeated.

An initial control mini MSC attempt measures 12064 stack bytes, below the test
target; its failure JSON is retained. The unchanged control retry and candidate
both pass at 12544. No limit was weakened. A late CDC echo is handled using the
existing correlated-response mode in the private HIL runner. Initial wrong
endpoint and macOS SET_CONFIGURATION host-test attempts are recorded separately;
the latter is ARM-only in the final host runner. Its host configuration was
restored programmatically. A simultaneous two-device DFU listing aborted mini
before erase/write; filtering the pinned serial resolves the ambiguity without
accepting broken descriptors or reducing identity checks.

Reproduction:

```sh
python3 tests/usb_fs_control_arm_self_test.py BUILD/compile_commands.json --json ep0.json
python3 tests/stm32f4_usb_arm_self_test.py BUILD/resident.elf
python3 tests/hil_usb_ep0.py --port PORT --public-id ID --expected-build CRC --strict --output ep0-hardware.json
```

ARM fixtures need Unicorn. Full measurements, failure notes and immutable image
hashes are in `doc/measurements/stm32-fixed-ep0-20261015.json`. Local raw artifacts
are retained in `.build/stm32-ep0-storage-buffers-20261015` outside the worktree.
