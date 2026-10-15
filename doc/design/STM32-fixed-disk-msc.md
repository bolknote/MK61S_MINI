# Fixed-disk MSC/BOT/SCSI

The transport is specialized for the calculator's virtual FAT disk: one LUN,
interface 0, bulk endpoints 0x81/0x01, Full Speed and 512-byte sectors. Disk
capacity still comes from the active virtual volume; it is not fixed to a
particular NOR chip. The disk's deferred read/write/sync lifecycle and power
write gate remain in place. NOR operations and USBDISK.APP execution remain
outside USB interrupt context.

The generic storage callback table and registration API are removed. C calls
connect the transport directly to the resident virtual-disk adapter. Shared
READ/WRITE(10/12) handlers replace four copies of block/byte conversion,
readiness and range handling. The implemented command set is retained:
INQUIRY (including VPD 00/80), REQUEST SENSE, TEST UNIT READY, START STOP,
ALLOW/PREVENT, MODE SENSE(6/10), READ FORMAT CAPACITIES, READ CAPACITY(10/16),
READ/WRITE(10/12), VERIFY(10), SYNCHRONIZE CACHE(10/16).

The transport state removes mutable LUN/interface/block-size fields, the
cached capacity and unused sense union/ASCQ. Every reported ASCQ remains
zero, and the four-slot sense ring retains its previous three-entry usable
capacity. The F411 transport changes from 8308 to 8264 bytes; its aligned,
retained allocation changes from 8312 to 8264 bytes. F401 keeps a static
512-byte-packet transport, now 584 rather than 628 bytes. F411's 8192-byte
packet and write-cache limits are retained; reducing the transfer buffer is
not part of this saving.

The rewrite also validates the actual received OUT length before submitting a
write, rejects CDBs shorter than their command group, and rejects deferred
completions after reset, teardown or a switch to CDC. READ FORMAT CAPACITIES
reports a block count, and fixed-format sense reports the correct additional
length. Host/device direction and length disagreements keep their phase
status. A short OUT transfer is discarded instead of persisting a stale
packet tail. Reset recovery preserves endpoint halt state until the host
clears both endpoints. Accepted eject remains latched across deferred sync
failures and a following ALLOW command.

The independent wire expectations follow [USB BOT 1.0, sections 3 and 6.7](https://www.usb.org/sites/default/files/usbmassbulk_10.pdf).
ST-derived source notices and the repository's USB middleware license are
retained; this specialization is not presented as independently authored
USB protocol code.


## Measurements and hardware

| Board | Flash before | Flash after | Flash saved | Static RAM | Retained MSC RAM saved |
|---|---:|---:|---:|---:|---:|
| Classic V3 UC1609 | 360136 | 359028 | 1108 | 28056, unchanged | 48 |
| mini V3 LCD1602 A00 | 332616 | 331476 | 1140 | 26728, unchanged | 48 |

These are matched LIBM test profiles, not every release configuration. The
control and candidate use the same path and feature flags. The previously
installed Classic control was 12 bytes larger due to build layout; that
unmatched difference is excluded. The 48-byte F411 saving occurs when MSC's
retained buffer is first prepared, not in `.data`/`.bss` at boot.

All 16 F411 and nine F401 variants pass their budgets; the four cross-MCU
WS0010 RAM comparisons pass. Source/archive gates pass on these 25 plus the
two installed test images. Actual controller and control/queue ARM tests
also pass with the Classic, mini and F401 settings.

Classic was installed and completely tested before installing mini. Both
boards pass binary MSC import/export, Unicode names, safe eject/CDC return,
reset, CDC boundary writes, 100 CRC-checked 64-KiB NOR reads, and exact
comparison of every original file and calculator state. Classic preserves
44 files and four directories; mini preserves ten files and three directories.
RTC correction/settings are untouched. CRCs are `4E665E6B` and `56F2CDFB`.

The 64-KiB NOR read medians (60 samples) are 24992 to 25001 us on Classic and
24804 to 24806.5 us on mini: changes of 0.04% and 0.01%, without evidence of
a reading-speed regression. The minimum candidate stack remainder is 12600
and 12544 bytes, above the 12288-byte test target. The initial unmodified
mini control once measured 12088; its failure is preserved, and subsequent
strict control and candidate runs both measured 12544. A first mini HIL
attempt also saw a transient absent CDC node before starting any MSC work;
the identity/CRC check and full retry passed without another flash.

The older retained-buffer ARM fixture depends on a WorkspacePartition symbol
that optimization removes from these ELFs. Its attempted run is recorded as
unavailable; no production test hook was added. Actual retained-reserve ELF
checks, real MSC allocation on both boards and the new transport fixtures
pass. No sleep diagnostic is armed; actual Mac suspend is not newly qualified
by this transport-only phase.

## Reproduction

The ARM fixture compiles the real class, BOT, SCSI, inquiry and memory sources
with an independent fake USB wire and deterministic disk. It runs on the
F411 and F401 memory layouts, checking all thirteen BOT cases, exact response
bytes, multi-packet READ/WRITE(10/12), deferred completion and failures,
malformed wrappers/CDBs, sector/range/overflow bounds, reset and halt recovery,
sense overflow, endpoint-open failure cleanup and 4000 random CDBs per MCU.
It does not replace the hardware USB controller model or physical tests.

```sh
python3 tests/msc_bot_scsi_arm_self_test.py BUILD/compile_commands.json --json protocol.json
MK61_TEST_SANITIZERS=1 tests/run_msc_scsi_safety_tests.sh
MK61_TEST_SANITIZERS=1 tests/run_usb_disk_session_tests.sh
python3 tests/usb_fs_control_arm_self_test.py BUILD/compile_commands.json
python3 tests/stm32f4_usb_arm_self_test.py BUILD/resident.elf
python3 tests/check_app_memory_elf.py BUILD/resident.elf
```

The ARM runner needs Unicorn with Cortex-M4 support and the pinned Arm GCC
compiler/includes from the build's compile database. It does not run on a
host reinterpretation of the firmware's ARM ABI.

Final same-path Flash/RAM measurements, firmware hashes, hardware results and
qualification details are recorded in
[stm32-fixed-disk-msc-20261015.json](../measurements/stm32-fixed-disk-msc-20261015.json).
