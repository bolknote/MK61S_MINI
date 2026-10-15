# MSC transport RAM scoped to a disk session

This follows the fixed-disk BOT/SCSI specialization in commit `252df65c3`.
F411 keeps the same 8192-byte packet and 8264-byte transport state. Its RAM is
now temporary: preparing a disk pins a non-moving buffer, while closing the
disk returns that region to the shared heap/OVERLAY/APP pool. Before the first
disk session the old lazy allocation was also absent; the benefit is after
that first session, when the old implementation kept the buffer forever.
F401 retains its existing static 584-byte transport and 512-byte packet.

The existing `shared_memory::OverlayBuffer` is available independently of the
experimental VM/USB Screen combination. A new, nonpersistent `USB_TRANSPORT`
owner uses it after the full FAT stage index and optional pinned USBDISK.APP
have acquired their final addresses. It borrows neither fixed WORKSPACE/BULK
nor the APP arena. The manager fences heap growth and both neighboring arenas;
a failed allocation leaves the existing disk index and APP intact. Every owner
number that predates this addition is unchanged.

Preparation materializes lazy WORKSPACE/BULK first. SET_CONFIGURATION still
performs no allocation, heap growth or APP call. USB reset and IRQ DeInit keep
the prepared buffer pinned for configuration retries within the same session.
Only the foreground close path can clear the prepared pointer, after stopping
and deinitializing the USB device and cancelling deferred work. It clears that
pointer before returning RAM to the manager. An unexpected live owner or
in-flight operation refuses release and reports `msc-release`, keeping the
buffer pinned rather than reusing referenced memory. Normal abort, startup
failure, finalization failure and repeated deinit all unwind the allocation.

The release ELF gate distinguishes retained buffers from session allocations.
Ordinary APP capacity no longer subtracts MSC permanently, but disk capacity
must still hold the actual USBDISK APP (rounded to 32 bytes), the full 2560-byte
stage index, and the session transport (rounded to eight bytes) simultaneously.
Static RAM and peak session RAM are reported separately from returned idle RAM.

## Measurements

The baseline is `252df65c3`; all feature flags, compiler, source epoch and
source path match. Flash counts include the sealed image.

| Board | Flash before → after | Static RAM before → after | Net RAM returned after closing MSC |
|---|---:|---:|---:|
| Classic V3 UC1609 | 359028 → 359352 (+324) | 28056 → 28072 (+16) | 8248 |
| mini V3 LCD1602 A00 | 331476 → 331824 (+348) | 26728 → 26728 (0) | 8264 |

During MSC the same 8264-byte state remains live. Peak RAM therefore increases
by 16 bytes on Classic and stays unchanged on mini. The saving applies to idle
operation after a disk session, rather than to the old pre-first-use boot state.
The fixed cache and packet sizes are unchanged.

Classic's real heap/free-pool readings after a control session are 61720 free
bytes, versus 69968 after the candidate session. Mini changes from 63048 to
71312. Six consecutive sessions per image run without an intervening reset;
the candidate prepared pointer is null after every close. Actual OVERLAY plus
APP capacities recover the complete free linker range. Classic additionally
passes two sessions with the capacity-reading probe. All own temporary files
are removed; all 44 original Classic files/four directories and ten mini
files/three directories retain their hashes and calculator state.

The 60-sample 64-KiB NOR medians change from 25001 to 25033.5 us on Classic
(+0.13%) and 24813 to 24809 us on mini (-0.02%). Core step medians change from
1709517 to 1712125 cycles (+0.15%) and 1707908 to 1708303 (+0.02%). Classic's
fresh-reset repeat gives 25033 us/1712124 cycles. These are measured small
differences, not an assertion of identical timing or a USB throughput result.
The normal binary MSC tests retain the 12288-byte stack target and pass with
12632/12544 bytes remaining. Firmware stack/guard budgets are unchanged.

Qualified hardware CRCs are `B8E3A516`/`FA8F1A9C`. After qualification Classic
was handed back to the authorized numeric-IF task for its separate A/B/A test,
with the immutable `B8E3A516` restore image and preserved state; that task may
temporarily run another image. No physical Mac sleep test is added here.

## Qualification

The production manager runs under ASan/UBSan through 100 simultaneous
APP/stage/transport allocation, OOM, teardown and reuse cycles. A Cortex-M4
fixture compiles the real foreground bridge, manager and class/BOT/SCSI sources
with only media/controller mocks: five suites, 50 successful sessions, all startup failure
points, failed finalization, OOM, idempotent close, pending read/write/sync cancellation,
repeated reset during real read/write processing, and reuse after close.
The existing independent protocol fixture adds active-owner, IRQ-only release,
wrong-pointer, configuration-retry and recycled-packet checks; its 22 suites
include all 13 BOT matrix cases and 4000 random CDBs on each MCU.

`hil_msc_session_ram.py` uses a small ordinary qualification APP, bound to an
exact sealed ELF/BIN pair. It reads the actual heap cursor, prepared pointer,
fixed-arena backing pointers, and APP/OVERLAY capacities, then writes small
report files through public file services. It introduces no firmware diagnostic API or
production test hooks. The heap comparison accounts for first-use materializing
of lazy WORKSPACE/BULK, so that is not mistaken for an MSC leak. It performs
repeated 4096-byte Unicode-name file transfers and safe ejects without resetting
between sessions, then removes its own APP/reports/files and checks all original
file hashes, program, registers, stack and current directory. Physical testing
runs on Classic before mini. The qualification APP is not a System APP to ship.

```sh
MK61_TEST_SANITIZERS=1 tests/run_memory_buffer_tests.sh
python3 tests/msc_bot_scsi_arm_self_test.py BUILD/compile_commands.json
python3 tests/msc_session_bridge_arm_self_test.py MINI_BUILD/compile_commands.json
python3 tests/check_app_memory_elf.py BUILD/resident.elf
python3 tests/experimental/prepare_msc_session_ram_app.py \
  --bin SEALED.bin --elf SEALED.elf --arm-toolchain-bin ARM_BIN --output-dir PROBE
python3 tests/hil_msc_session_ram.py --port PORT --public-id ID \
  --fixture PROBE/resident.json --app PROBE/MSCRAM.APP --output-dir RESULT --cycles 6 --minimum-stack-remaining 11264
```

The additional APP/file-service workload uses an explicit 11264-byte test
threshold on both images: the initial old Classic control once measured 12152,
below the ordinary MSC target. That incomplete attempt and successful cleanup
remain in the report; ordinary MSC still passes its separate 12288-byte gate.
The mini snapshot was refreshed immediately before testing because its current
X differed from an earlier snapshot; the older copy was preserved and never
written back. Late terminal echoes after reset are handled by an empty-line
stream handshake in the HIL runner, with strict identity checks before writes.

ARM fixture commands need Unicorn. A full release qualification also builds
all 16 F411/nine F401 variants and runs their source/archive and RAM contracts.
The installed-image measurements are recorded separately in
`doc/measurements/stm32-msc-session-buffer-20261015.json`.
