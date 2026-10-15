# Compact native USB state

This change specializes the owned USB state for the existing, mutually exclusive
Full Speed CDC/MSC device. Its baseline is main `18361c3a4`. The native and legacy
Arduino layouts are selected explicitly; the legacy layout and supported Flash
geometries remain available.

## Layout

| ARM object | Before | After |
|---|---:|---:|
| USB device handle | 252 | 96 |
| CDC handle | 36 | 28 |
| Logical endpoint record | 20 | 4 |
| CDC/MSC callback table, each (Flash) | 56 | 36 |
| Hardware endpoint table, all eight directions | 128 | 128 |

All four IN and four OUT logical slots remain. Only EP0 needs independent
remaining/total counters in each direction, so its two pairs of **32-bit**
counters move out of the eight endpoint records. Per-endpoint records retain
persistent 16-bit status replies, packet size and the used flag. Packet size is
bounded by the existing Full Speed contract and EP0 is asserted to be 64 bytes.
No packed structures, unaligned pointers or narrowed transfer counters are used.

Unused configuration/BOS/composite bookkeeping is removed from the native
handle. Valid device states, configuration, class index and flags use bytes;
request values and indices still undergo the complete existing wire checks.
One authoritative class-data pointer replaces the duplicated scalar and array
slots. Typed accessors support the native and legacy layouts without union
aliasing. Every USB compilation unit uses the same forced public headers.

The CDC handle retains aligned payloads, pointers and full 32-bit RX/TX lengths.
The unused RX state disappears; TX state distinguishes idle, payload and pending
ZLP. An exact multiple of 64 still produces exactly one trailing ZLP before its
completion callback. The owned queue sets TX buffers only while idle under
its interrupt guard, so TX length stays stable until completion. Busy, disconnect and reset semantics remain covered by the
production ARM model. Unsupported ISO/HS/other-speed callback slots disappear
from native class tables; the existing Full Speed callbacks and descriptors stay.

The controller table keeps its eight directions and 32-bit counters, including
reporting malformed oversized OUT transfers without copying beyond capacity.
TX/RX queue sizes, MSC packets, read caches, APP budget, stack/guard and descriptor
bytes are unchanged. No NOR driver or geometry implementation is modified.

## Matched resources

Controls and candidates use identical build/source paths, compiler, profile
flags and SOURCE_DATE_EPOCH 1791969300. Flash includes the sealed footer. Static
RAM is the release gate sum of `.data + .bss + .noinit`.

| Board | Flash before → after | Static RAM before → after |
|---|---:|---:|
| Classic V3 UC1609 | 360752 → 360564 (−188) | 27048 → 26880 (−168) |
| mini V3 LCD1602 A00 | 333200 → 332996 (−204) | 25704 → 25536 (−168) |

The handles themselves save 164 bytes; the final linked static regions save 168
because alignment also changes. Callback tables save 40 Flash bytes in total;
the complete Flash delta includes the changed accesses and EP0 bookkeeping.
The comparison is against the recorded baseline, not concurrent later changes
on main. Maximum native frames stay 1928/1960 bytes.

## Qualification

The immutable-source matrix builds all 16 F411 and nine F401 variants with their
original source/archive, APP RAM, frame and product limits. Four WS0010 cross-MCU
RAM comparisons retain their original limits. An absolute layout-version symbol
selects the exact 96/28-byte native ABI in the release ELF gate; the 252/36-byte
legacy ABI remains separately checked. Unit regressions reject mixed layouts,
missing/unknown markers and wrong object sizes.

Eight ARM compile probes cover native/legacy C/C++ on F401/F411, including
natural alignment and full counter widths. Two negative probes reject unsupported
multi-class/composite native configurations. The nine EP0 ARM suites include
all 65536 interface/endpoint indices, persistent two-byte replies with adjacent
field canaries, independent counters above 65535, segmentation, ZLP, reset,
suspend/resume, failed/repeated configuration and 50000 queue transitions.

The actual Classic CDC image checks lengths 0, 1, 63, 64, 65, 128, 65535, 65536
and 65600, preserving exact requested lengths and one-ZLP completion. Its test
reads the actual ELF object size and observes the real RX setter instead of
assuming historical offsets. Queue calls use their declared pointer argument,
which also permits the real mini no-LTO release variant. The mini LTO entry is
inlined, so its exact shipping image is covered by controller and physical tests.
Both boards' actual controller models and five foreground MSC lifecycle suites
pass; BOT/SCSI executes 22 suites across both MCUs. ASan/UBSan allocator stress,
SPI NOR SFDP variants and USB STOP/power tests retain their checks.

Hardware qualification installs the candidate on Classic before mini. Each
sealed ELF/BIN pair has a bound RAM probe for four consecutive MSC sessions
without reset between sessions. The ordinary binary MSC test retains its 12288
stack target; the separate RAM/file-service workload retains 11264 on both
control and candidate. Physical EP0, Unicode-name 4096-byte import/export,
CDC boundary files, CRC-checked graphics frames, NOR/DMA and core timings
accompany full original-file and calculator-state comparison.

Graphics qualification uses the existing reset-after-cleanup workaround only
when original registers/stack/program are zero/empty; that precondition is
checked by the existing runner. It does not claim to repair screen-session
cleanup. Physical Mac sleep is not repeated; ARM transitions and linked suspend
gates are checked. Detailed results, exact images and qualification notes are in
`doc/measurements/stm32-usb-compact-state-20261015.json`.

Local artifacts stay outside the worktree in
`.build/stm32-usb-compact-state-20261015`.


## Physical results

Both complete candidate qualifications passed in the requested Classic→mini
order. Every original file and calculator program/register/stack/current-directory
comparison is exact. All temporary APPs, reports and file fixtures were removed.
The RAM loan is returned after every one of four consecutive disk sessions.

| Measurement (control → candidate) | Classic | mini |
|---|---:|---:|
| Idle pool free, bytes | 70992 → 71160 | 72336 → 72504 |
| Core step median, cycles | 1709891 → 1712123 | 1708390 → 1711026 |
| Raw 64-KiB NOR median, µs | 25003.5 → 25003.0 | 24763.5 → 24802.0 |
| Ordinary MSC minimum stack remaining, bytes | 12624 → 12632 | 12544 → 12544 |

Each NOR median uses 60 reads; core medians use five restored batches of 40
steps. Core timing changes by about +0.13/+0.15%; NOR by less than 0.2%.
These observations establish no general execution-speed improvement. The
emulator, mathematics, SPI transport and NOR implementations are unchanged.

On the first Classic candidate attempt, binary data, ejection, reset and cleanup
completed, then a separate-port MPU read timed out. Reopening the port **without
a firmware reset** immediately returned valid identity/CRC/MPU and no crash.
Twenty `df`/MPU pairs across 40 open/close sessions then passed. The strict full
repeat reads each command and its watermark in one identity-checked DTR session;
all original checks and thresholds remain. That repeat, four RAM sessions and
103 graphics frames passed. The original failure and recovery reports are
retained. The root cause is not established; no firmware workaround is claimed.

Candidate images:

- Classic: CRC `122A5FF9`, 360564 bytes; BIN SHA256 `059bff2d4d2aba948ba75ba382f52c4c7593439156be6ec045d674002f7db1da`.
- mini: CRC `979046B7`, 332996 bytes; BIN SHA256 `1f76bd0e510a1b5913275a6f9a43cfa0bdf9b7b2acc784dad38504297b871a92`.

After final health verification and closing all ports, Classic was released to
the authorized VM-blocks task. Its current recovery pair is the immutable
`install-candidate/classic.bin` and matching `.elf` in the artifact folder.
Subsequent work in that task is outside these results. Mini qualification
correctly ignored the other Classic's DFU node by its pinned USB location.

Representative regression commands:

```sh
python3 tests/usb_state_layout_compile_self_test.py BUILD/compile_commands.json --json layout.json
python3 tests/usb_fs_control_arm_self_test.py BUILD/compile_commands.json --json ep0.json
python3 tests/msc_bot_scsi_arm_self_test.py BUILD/compile_commands.json --json bot.json
python3 tests/msc_session_bridge_arm_self_test.py BUILD/compile_commands.json --json bridge.json
python3 tests/stm32f4_cdc_arm_self_test.py CLASSIC/resident.elf
python3 tests/stm32f4_usb_arm_self_test.py BUILD/resident.elf
MK61_TEST_SANITIZERS=1 bash tests/run_memory_buffer_tests.sh
MK61_TEST_SANITIZERS=1 bash tests/run_spi_nor_sfdp_tests.sh
```

ARM runners require Unicorn with Cortex-M4 support. The CDC model's direct init
entrypoint also exists in the supported no-LTO mini variant. The physical tests
use the exact sealed shipping candidates, not those diagnostic variants.
