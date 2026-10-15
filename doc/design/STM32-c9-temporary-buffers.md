# Scoped C9 catalog buffers

This stage follows fixed EP0 (`fa7f5b61c`). On F411 the catalog I/O buffer and
pending checkpoint table no longer occupy permanent BSS. Short foreground
phases borrow non-moving storage from the existing guarded dynamic pool and
return it immediately. The two 512-byte inode read-cache lines, packet/cache
sizes, data format, node quota, maximum NOR capacity, APP limit and firmware
stack/guard are retained.

A catalog table now stores aligned CRC32 values separately from 16-bit physical
sector references: 312 rather than 416 bytes for all 52 possible pages. The
128-MiB geometry has at most 32768 erase sectors. Empty references expand back
to the unchanged on-disk 0xFFFFFFFF value. Mount validates each complete 32-bit
on-disk reference before narrowing, so malformed high bits cannot alias a
valid page. Only checkpoint owns a pending table; its pointer and sector pins
are cleared on every return path.

`OverlayBuffer` permits one live buffer per owner in strict LIFO order. The
first buffer fences ordinary OVERLAY growth; the last buffer fences APP and
heap growth. Adding catalog and I/O buffers cannot move the original USB packet
or evict an APP. IRQ acquisition, duplicate owners, invalid sizes and failed
allocation leave all existing owners intact. Old owner numbers are preserved.

CRC scans, WAL serialization/replay and immutable FAT verification use a
512-byte I/O loan. WAL releases its loan before recovery or bitmap verification
can acquire another. FAT preparation keeps its separate private bitmap because
source callbacks may read C9 themselves. Checkpoint page streaming and root
serialization use that same I/O loan in distinct phases. Page allocation proofs
finish before pinning the raw page buffer, avoiding a nested I/O alias.

A pre-existing contract permits ordinary file operations while an unrelated
non-evictable client holds the entire OVERLAY range. Separate noinline fallback
functions therefore retain bounded stack storage when a loan cannot fit. The
normal path does not reserve those arrays on entry. No heap allocator, newlib
archive or eviction is introduced. The fallback can use additional transient
stack; the existing stack budget and frame checks remain authoritative.

The ELF gate charges the simultaneous 824-byte filesystem reserve (312-byte
pending map plus 512-byte I/O), in addition to the maximum APP, full 2560-byte
stage index and 8264-byte MSC transport. It also qualifies maximum ordinary APP
plus filesystem scratch. Scoped allocations do not masquerade as permanently
free RAM during a disk transaction. F401 retains its stack-I/O configuration
and static pending map, with compact maps and unchanged release limits.

## Resources

Matched sealed images use the same source/build paths, feature flags, compiler
and SOURCE_DATE_EPOCH as EP0. Both F411 boards free 1024 static bytes. The
operation can temporarily use 824 bytes of that returned space. Flash grows
because the manager, phase scopes and full-pool fallback preserve existing
behavior.

| Board | Flash EP0 → C9 | Static RAM EP0 → C9 |
|---|---:|---:|
| Classic V3 UC1609 | 359200 → 360256 (+1056) | 28072 → 27048 (−1024) |
| mini V3 LCD1602 A00 | 331656 → 332704 (+1048) | 26728 → 25704 (−1024) |

Across both EP0 and C9 stages, relative to starting main `57835a271`, Classic
uses 696 more Flash bytes and 1024 fewer static RAM bytes; mini uses 704 more
Flash bytes and 1024 fewer RAM bytes. Maximum native frames remain 1928/1960
bytes. The ordinary checkpoint path no longer keeps a 512-byte raw page or root
header array on stack; actual cumulative hardware watermarks are reported
separately.

## Verification

ASan/UBSan runs the production C9 implementation with software and emulated
STM32 CRC backends, both scoped and legacy storage modes, torn writes/reads,
power-cut recovery, GC/rotation/full-store refill and maximum-capacity staging.
Added regressions reject full-width corrupt catalog references and exercise
20 real write/checkpoint/read/remove cycles with pinned maximum APP, full stage
and the unchanged USB packet. The existing completely occupied OVERLAY test
remains enabled. The memory manager additionally runs 100 nested prepare/OOM/
release/reuse cycles with byte canaries. VFAT mutation/import tests, Cortex-M4
BOT/SCSI and lifecycle fixtures and all 25 release variants pass their original
limits. The four cross-MCU WS0010 RAM comparisons remain required.

Hardware qualification proceeds Classic before mini. Exact sealed ELF/BIN
bound RAM probes check actual pool coalescence after four consecutive disk
sessions per image, without reset between sessions. Ordinary binary MSC keeps
its 12288-byte stack test target. The additional APP/file-service RAM workload
uses its prior separate 11264-byte target on both control and candidate; firmware
limits are unchanged. Physical EP0, CDC boundary files, raw NOR CRC/DMA checks,
three cold reads per file after independent resets, 57 warm file reads per file
and core-step timings accompany complete original-file and calculator-state
comparison. Physical Mac sleep is not repeated.

Initial experiments and incomplete HIL attempts remain in the local artifact
folder. The first dynamic-only design failed the occupied-pool contract; its
fallback replaces that design. A first new stress fixture used invalid NUL-filled
TEXT; the qualified fixture uses ordinary text without relaxing validation.
Initial matrix failures came from stale reference paths and an F401 Werror on
a constant pointer; the final immutable-source matrix is recorded separately.

Final hardware figures and exact hashes are recorded in
`doc/measurements/stm32-c9-temporary-buffers-20261015.json`.


## Hardware results

Classic completed qualification before mini was installed. Both passed physical
EP0 requests, two binary MSC import/export/eject/CDC-return cycles, reset
persistence, CDC boundary transfers, NOR CRC/DMA checks and state preservation.
Original data remained exact: Classic 44 files and four directories; mini ten
files and three directories. The RAM probe was bound to each sealed ELF/BIN pair
and ran four consecutive disk sessions without reset. Every close returned the
same complete pool and cleared the prepared transport owner.

| Measurement (EP0 → C9) | Classic | mini |
|---|---:|---:|
| Idle pool free, bytes | 69968 → 70992 | 71312 → 72336 |
| Ordinary MSC minimum stack remaining, bytes | 12632 → 12600 | 12544 → 12540 |
| Four-session APP workload minimum stack remaining, bytes | 12608 → 12600 | 12544 → 12464 |
| Raw 64-KiB NOR read median, µs | 25032 → 25006 | 24812 → 24774.5 |
| Core step median, cycles | 1709889 → 1709968 | 1711027 → 1708304 |
| Cold 1-KiB BIN read median, µs | 1134 → 1141 | 989 → 996 |
| Cold compressed 1-KiB TEXT read median, µs | 1297 → 1296 | 1158 → 1157 |
| Warm file read median, µs (both files) | 35 → 35 | 35 → 35 |

Cold BIN reads therefore cost about 0.6–0.7% more; three independent resets
per file expose that cost instead of hiding it behind the retained read cache.
Each raw NOR median uses 60 samples, each warm-file median 60 samples, and each
cold-file run includes 19 subsequent warm reads. Core timing uses five sets of
40 steps. These observations do not establish a general execution speedup.

The ordinary MSC stack target remains 12288 bytes. The separate APP/file-service
RAM workload retains its 11264-byte target for both control and candidate.
All measured minima pass. The 16-KiB firmware stack and 256-byte guard are
unchanged. The idle pool numbers are actual coalescence measurements; they do
not subtract a lazy VM cache. The ELF gate separately charges all retained
workspace, bulk and VM cache storage before testing simultaneous owners.

Qualified final images:

- Classic: CRC `E52F87BE`, 360256 bytes; BIN SHA256 `88055774bbda4b98b1708667472b5e020133f0a131840ef6ef3d14ac00a5c530`.
- mini: CRC `15089F31`, 332704 bytes; BIN SHA256 `eb9ef2847786c0a07d9b5275d3e7d07590072fb84832c90b4dc4e9922cfb4132`.

After both boards passed and all ports closed, Classic was released to the
separately authorized byte-code task. Its recovery image is the immutable
`install-fs/classic.bin` plus matching `.elf` in the raw artifact folder. Later
experiments in that task are outside these measurements. The EP0-only D80CE1D1
image remains an archived control, not the current recovery image.

Representative local regressions, run from the repository root:

```sh
MK61_TEST_SANITIZERS=1 MK61_TEST_STORAGE_SHARED_TEMP=1 bash tests/run_program_store_tests.sh
MK61_TEST_SANITIZERS=1 MK61_TEST_STORAGE_SHARED_TEMP=1 bash tests/run_program_store_tests.sh --stage-max-capacity
MK61_TEST_SANITIZERS=1 MK61_TEST_STORAGE_SHARED_TEMP=1 bash tests/run_virtual_fat_tests.sh
python3 tests/app_memory_elf_self_test.py
python3 tests/usb_fs_control_arm_self_test.py BUILD/compile_commands.json --json ep0.json
```

The existing completely occupied OVERLAY regression is also required in legacy
storage mode. Production release qualification includes all 25 matrix variants,
their original source/archive/APP-memory checks and the four WS0010 cross-MCU
comparisons. The measurement JSON records source hashes and the production
diff hash shared by the final matrix and both installed images. Raw logs remain
in `.build/stm32-ep0-storage-buffers-20261015` outside the worktree.
