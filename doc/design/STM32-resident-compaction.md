# Compact resident state and foreground buffer lifetimes

The comparison starts at main `b0c7528a2`. It freezes the same source/build paths,
GNU Arm GCC 14.2.1, 96 MHz F411 profiles, feature flags and
`SOURCE_DATE_EPOCH=1791969300`. Later independent VM changes on main are outside
these measurements. The work is on `feature/stm32-resident-compaction`.

## Representation and lifetime

The 90-entry emulator bank map uses one-byte, one-based slot indices instead of
ARM pointers. Zero denotes an absent bank. All 32 backing slots, sparse high
addresses and overflow rejection remain. Staging combines its seven-bit record
count and sealed bit in one byte per sector. Together they save 400 static bytes.

F411's M61 labels, 1024-byte read cache and return frames now live in one scoped
buffer. All capacities remain. Root scripts acquire it; nested scripts and
WATCH_EVENTS keep it. Cancellation, error and completion release it after hooks
are cleared. Placement construction explicitly starts the C++ object lifetime.
Allocation failure reports an error without overwriting another owner.

A full 192×64 USB framebuffer exists only during an attached session or an
explicit display loan. Classic keeps its ordinary 192-byte page. Rejected
attaches release pending storage. Detach restores the physical view before
unbinding the framebuffer. Pending packets use the session-owned snapshot,
which is copied before asynchronous transmission.

The filesystem's 1536-byte writer/batch/sidecar workspace is scoped. Its 1024+512
partitions preserve nesting/exclusion rules. A fully pinned OVERLAY was already
allowed to coexist with local writes, so a separate bounded stack fallback
preserves that contract. Only lease failure selects the fallback: a failed
operation never runs twice. The normal path does not reserve that stack array.

`LifetimeBuffer` adds independently releasable high allocations to the guarded
pool. It never moves a live APP or buffer and does not use malloc. APP may start
before or after M61/screen and either may finish first. Released high gaps are
reused; the full prefix returns when the last owner leaves. Existing short
`OverlayBuffer` loans retain LIFO rules. New owner IDs are appended. IRQ,
duplicate-owner and invalid requests leave current owners intact.

Native F411 defaults to `MK61_SCOPED_RESIDENT_BUFFERS=1`. F401, portable System
APPs and legacy builds retain permanent/stack storage as appropriate. The zero
setting retains all functions with permanent buffers. The resident manager
header is imported only where shared storage is enabled; USBDISK.APP keeps its
separate portable ABI declarations.

C9 serialization copies the natural 22-byte little-endian prefix and explicitly
writes the final 32-bit address across the two RAM padding bytes. Static
assertions pin all field offsets; the disk format stays 26 bytes. Empty-inode
and scalar endian handling remain. Linked codec wrappers shrink 318→138 bytes.
Terminal dispatch forwards results directly and clears input through one scope
guard, preserving script/trap actions and the original initial validation.

## Matched resources

Flash includes the footer. Static RAM is `.data + .bss + .noinit`.

| Configuration | Classic Flash | Classic RAM | mini Flash | mini RAM |
|---|---:|---:|---:|---:|
| Baseline | 360564 | 26880 | 332996 | 25536 |
| Compact bank/stage | 360500 | 26480 | 332932 | 25136 |
| Scoped M61/filesystem, intermediate | 361176 | 22880 | 333608 | 21536 |
| Scoped framebuffer, intermediate | 361304 | 21552 | 333688 | 20016 |
| Final default | 361816 | 21552 | 334360 | 20016 |
| Final, permanent buffers | 360292 | 26480 | 332868 | 25136 |

The final default frees 5328/5520 static bytes at a cost of 1252/1364 Flash bytes.
The lifetime manager and full-pool fallback cost code; smaller individual
serializers/terminal paths do not imply a net Flash saving. The permanent-buffer
alternative saves 272/128 Flash bytes and 400 static RAM bytes.

These are **idle/static** savings. M61 rounds to 2112 dynamic bytes, the screen
needs 1536, and filesystem operations can need another 1536. The APP ELF gate
charges all 5184 simultaneously, plus the existing retained 40960, maximum APP
20480, full staging 2560, MSC 8264 and filesystem temporary reserve 824.
Another 224 bytes account for worst-case APP end alignment. The conservative
effective pool changes 46560→46496 on Classic and 47904→48032 on mini.
High gaps are not counted as contiguous OVERLAY capacity. Maximum
concurrency does not gain 5 KiB.

APP limits, 16-KiB runtime stack/guard, NOR variants/geometries, cache capacities,
display geometry and USB queues remain. Maximum native frames stay 1928/1960
bytes; the occupied-pool fallback frame is 1544.

The intermediate dynamic-only filesystem version failed the existing occupied
pool test. It is not qualified by its size alone; the final fallback replaces
it. Whole-terminal size optimization and an Oz dispatch trial increased Flash
and were removed. Hot core, mathematics and raw NOR transfers were not rewritten.

## Displaced APP execution and MPU

Physical Classic qualification found a real integration regression: a newly
loaded graphics APP below the framebuffer was rejected because the original MPU
setter required its end to equal guard_base. A small preloaded diagnostic APP
kept reusing its cached top address, so allocator-only and warm diagnostic tests
had missed that contract. The fixed HIL starts each owner order with a cold APP
loader and loads the diagnostic after the buffers exist.

The loader deliberately retains an unchanged APP as a cache. Reopening the
same diagnostic can therefore preserve a middle lease after a buffer above it
has ended; the allocator must not move that image. The HIL alternates two
separate probe inodes to force actual eviction/reallocation before measuring
full coalescence. It retains the exact gap/ownership and stack assertions.

The setter now validates and programs the exact [begin,begin+size) lease. Five
positive MPU regions cannot cover every arbitrary 32-aligned interval of up to
20 KiB; a real six-region counterexample is retained. APP placement therefore
keeps its end 256-aligned below live buffers, with at most 224 bytes of slack.
The complete 20-KiB APP limit and the existing five slots/stack/guard remain.
The ELF gate charges that slack. It does not grant execution to the framebuffer,
M61 state, allocator gap, globals or stack.

The policy test exhausts 260800 placements and independently decodes actual
base/size/subregion fields. The production ARM setter additionally checks 247
spans per shipping image against every 32-byte SRAM granule, plus 12 coupled
production allocator/MPU cases; seven invalid
requests preserve all MPU registers, and clearing an APP restores SRAM XN.
Unchanged initialization is modeled in its exact shipping layout because LTO
inlines it; the setter itself executes directly from the resident ELF.

## Verification

- ASan/UBSan: all 32 bank slots, sparse address 9999, slot 33 refusal, clear/reuse
  and the exhaustive native core corpus.
- Lifetime allocator: all 36 create/release permutations with pinned staging,
  unchanged 20-KiB APP and MSC sizes, 6000 independent gap-oracle steps,
  canaries, heap bounds and allocation failures.
- M61: four cache/storage modes, nested scripts, WATCH_EVENTS, cancellation,
  error, OOM and APP survival when a script finishes first.
- Filesystem: software/STM32 CRC, F411 large-font path, full/refill, torn writes,
  reclaim and wear cases. Maximum staging still covers 128 MiB.
- Workspace: normal/fallback nesting, owner exclusion, one execution on false,
  exception cleanup and reuse. The host model credits the old 1536-byte payload
  moving into its simulated pool and charges 64 bytes of host metadata; existing
  APP/stage/MSC sizes and assertions stay.
- Display: five full pixel variants, 100 attach/detach cycles, failed AE, OOM
  and independent APP/M61/framebuffer release.
- C9: 10000 golden records × eight alignments in native/scalar modes, exact tail
  bounds and padding canaries; 1600 production ARM calls per shipping image.
- Terminal: 2304 legacy return cases and 193316 IF/script differential cases.
- Release: 16 F411 and nine F401 variants, unchanged source/archive, APP RAM,
  frame/Flash/product gates and four WS0010 cross-MCU RAM budgets. Full matching
  System bundles include portable USBDISK.APP.
- Actual ARM: startup/time/STOP, both USB controllers, CDC, EP0, BOT/SCSI, MSC
  lifecycle/layouts, 1897 math vectors and IEEE boundaries, EABI and ISO strings.

Exact results are in `doc/measurements/stm32-resident-compaction-20261015.json`.
Full logs, immutable images and snapshots remain outside the managed worktree
in `.build/stm32-resident-compaction-20261015`.

The lifetime HIL probe is an ordinary APP bound to the exact sealed ELF/BIN. It
reads allocator metadata and uses the ordinary file service for its report. It
checks both activation orders, an M61 callback, cancel with screen attached,
detach with watcher active, APP coexistence and full idle coalescence. The
zero/empty calculator precondition is checked before opening a root M61. No
production diagnostics or private-function calls are introduced.

## Physical qualification

Classic completed and was fully restored before the fresh mini snapshot.
Each board used matched sealed baseline/candidate binaries and matching System
APPs. Classic used `D6873FBC`/`80056CAE`; mini used
`5D8A15BA`/`740B8779`. ELF/BIN hashes and the frozen production input hash are
recorded in the JSON evidence. The production commit is `e326c7fb9`; the final
cold-loader/cache-eviction test commit is `32712c421`.

Both image pairs pass 50 physical EP0 requests, at least 100 matching graphics
frames, all 12 lifetime samples, ordinary MSC import/export and four additional
disk sessions without intermediate resets. The diagnostic tests load a real
APP after the watcher/framebuffer exists and verify full idle coalescence.
DMA/CRC and 1/63/64/65/255/256/257/4095/4096-byte filesystem boundaries pass.

The unchanged Classic control's complete successful graphics, disk, RAM,
driver and timing reports were retained. After the test-only cold-loader and
two-inode improvements, EP0 and the new lifetime workload were rerun on that
same control image; the final candidate ran the full suite again. Mini ran a
fresh full control and candidate sequence. The permanent-buffer alternative
was qualified locally, including its ARM/ELF gates; it was not flashed.

| Physical metric, control → candidate | Classic | mini |
|---|---:|---:|
| Idle guaranteed free bytes | 71160 → 76488 | 72504 → 78024 |
| Emulator cycles per step | 1712124 → 1709638 | 1711027 → 1711103 |
| Minimum ordinary MSC stack remaining | 12568 → 12536 | 12520 → 12344 |
| Minimum repeated-disk stack remaining | 12592 → 12536 | 12536 → 12344 |

Step timing is the median of five restored 40-step means. Changes are
−0.145% on Classic and +0.004% on mini, not a claimed speed optimization.
The 512/4096/65536-byte raw reads stay equal within 0.032%; a 64-byte read
changes by 0.5 µs on both boards. Warm file reads remain 35 µs; cold reads
change by at most 1 µs. Twelve ADC samples and 100 repeated 64-KiB SPI reads
with display traffic also pass; DMA and ownership error counters remain zero.

The ordinary MSC threshold remains 12288 stack bytes; the separate repeated
RAM workload keeps its existing 11264-byte threshold. Stack size/guard and
tests were not reduced. Each disk run returns to the same heap address,
with no prepared MSC buffer retained.

Every original file and directory is restored byte for byte: Classic 44/4,
mini 10/3. Program banks, registers, stack, current directory and alarm slot
settings match their snapshots. Final firmware/CRC/crash checks pass on the
immutable original images `122A5FF9` and `979046B7`. Each qualification closes
its CDC port after restoration. Recovery images and snapshots stay outside the
managed worktree.

## Integration with current main

The paired A/B above deliberately remains based on `b0c7528a2`. Before merging,
feature `09060ce2d` was combined with main `119c92761`, which already includes
independent BASIC graphics, integer VM spans and terminal changes. Those
features increase absolute resource use compared with the older frozen base.

| Merged default image | Flash | Static RAM | Conservative effective pool |
|---|---:|---:|---:|
| classic | 374688 | 24976 | 43072 |
| mini | 346512 | 23424 | 44608 |

All 13 integration groups pass: both native builds with matching complete
System bundles and APP/frame/driver/source/archive/suspend gates, actual ARM
MPU/C9, plus host memory, terminal/assembler, UI, BASIC graphics, M61,
filesystem, VFAT, MPU policy, C9, integer-span and raw24/raw32/mixed-cache
regressions. Sanitizers are enabled for the host suites that support them.
Existing wire10/request9 and the 5184+224 RAM charges remain.

This integration qualification is local; the physical checks above refer to
the exact frozen control/candidate images. Neither result replaces the other.
Merged-source hashes, absolute sizes and checks are recorded separately in
`doc/measurements/stm32-resident-compaction-main-20261015.json`.

Representative commands:

```sh
MK61_TEST_SANITIZERS=1 bash tests/run_memory_buffer_tests.sh
MK61_TEST_SCOPED_RESIDENT_BUFFERS=1 MK61_TEST_STORAGE_SHARED_TEMP=1 \
  MK61_TEST_SANITIZERS=1 bash tests/run_program_store_tests.sh
MK61_TEST_SCOPED_RESIDENT_BUFFERS=1 MK61_TEST_STORAGE_SHARED_TEMP=1 \
  MK61_TEST_SANITIZERS=1 bash tests/run_virtual_fat_tests.sh
MK61_TEST_SANITIZERS=1 bash tests/run_m61_text_tests.sh
MK61_TEST_SANITIZERS=1 bash tests/run_ui_display_tests.sh
bash tests/run_terminal_tests.sh
bash tests/run_mpu_guard_policy_tests.sh
python3 tests/mpu_app_arm_self_test.py BUILD/resident.elf
python3 tests/c9_inode_wire_arm_self_test.py BUILD/resident.elf
python3 tests/check_app_memory_elf.py --system-dir BUILD/System BUILD/resident.elf
python3 tests/check_foreground_stack_elf.py BUILD/resident.elf \
  --compile-commands BUILD/compile_commands.json
python3 tests/experimental/prepare_resident_lifetime_app.py \
  --bin BUILD/sealed.bin --elf BUILD/sealed.elf \
  --arm-toolchain-bin TOOLCHAIN --output-dir BUILD/lifetime-probe
python3 tests/hil_resident_lifetimes.py --port PORT --public-id ID \
  --keyboard-layout 1 --fixture BUILD/lifetime-probe/resident.json \
  --app BUILD/lifetime-probe/LIFERAM.APP --output-dir BUILD/lifetime-results
```

For a matched permanent-buffer comparison, use a **fresh** build directory with
`CXXFLAGS=-DMK61_SCOPED_RESIDENT_BUFFERS=0` and
`CFLAGS=-DMK61_SCOPED_RESIDENT_BUFFERS=0` in the environment of
`tools/.mk61-gcc/build-standalone.py`. These CMake initial flags must not leak
into the default build directory.
