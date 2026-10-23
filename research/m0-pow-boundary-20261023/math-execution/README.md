# V138 math execution package

Offline package for exact build **83CF4AC4**. No hardware has been accessed.
The immutable V138 source, ELF, BIN, UF2, footer, image extent and CRC are
unchanged. This directory is a private measurement package, not a release.

The transaction owner installs V138 and the separate diagnostic Qfplib span
only after review and human consent. It also owns all fresh snapshots,
full-Flash backup/readback, cold observability, platform checks and exact
rollback. This package implements only the math execution stage.

`execution-manifest.json` is the machine-readable target/artifact/step/addon
contract. It pins every APP, input, oracle, runner, reference and relevant
dependency. `execution-manifest.sha256` identifies this precise revision.
Runtime project helpers are extracted into frozen_helpers.py, with a
stdlib-only import closure. Their hashes are verified before any project
code is imported. The executor works independently of CWD and canonical
test/tool WIP; offline build dependencies are archived as copies.

## Reference and memory

`reference/reference.bin` contains6,364 Qfplib bytes at0x10180000. It is
identical to the earlier pinned reference, with no undefined imports or
RAM state. `reference/reference-sectors.bin` pads that code with0xFF to two
whole4KiB sectors: [0x10180000,0x10182000). The corresponding standalone
UF2 touches only those sectors. It is a separate diagnostic write scope;
the original firmware CRC does not cover it.

`layout-proof.json` checks actual V138 Flash LOAD segments, the firmware
erase boundary0x10178000, both linked settings Flash writer calls and the
persistent settings span [0x101FE000,0x10200000). The reference span is
semantically unallocated by V138. Live non-erased bytes there still belong
in the transaction's fresh full backup and exact final restore.

The transaction must separately read back the complete addon and exact
V138 prefix before any APP call. The math runner requires the fresh full
2MiB post-install readback at the path passed in `--verified-flash`.

TIMING.APP uses11,264 heap bytes, below the30,520-byte V138 heap. It has
no keyboard calls, physical key waits, interactive FOCAL wrapper, startup
screen wait or terminal recovery loop. It checks the exact26 runtime slots,
firmware CRC word, a reference fingerprint and reported125MHz clock outside
timing. Its8-word GUARD.bin receipt confirms the pre/post clock and guards.

## Workload and output

The main corpus remains117 groups /119 chunks /23,352 cases. Every frozen
expected result was independently revalidated with directed MPFR or exact
conversion/comparison rules. One supplementary30-case public-pow chunk
exercises negative-factor products. It is excluded from the117 performance
groups. `path-coverage.json` proves the combined public-pow inputs reach all
selected changed integer/root/midpoint/comparator paths on exact V138.

There are120 APP launches, each with1 second warmup and12 calibrated
rounds, six opposite-order pairs. Interrupts remain enabled. Both libraries
use identical input order, the owned code keeps its production Flash/SRAM
placement, and the reference keeps its previous Flash address. Raw own,
Qfplib, control and XIP counter series are saved per chunk. Qfplib errors
against the oracle are logged without treating its outputs as the oracle.

TIMERAWL measures microseconds. At checked125MHz, reported cycle equivalents
are elapsed microseconds times125, with125-cycle quantization per batch.
These are physical timed batches, not a separate exact core cycle counter.
The packet does not claim hardware cycles before a physical run.

Expected wall duration is12–20 minutes, based on an earlier87-chunk run
taking530 seconds; the stage timeout is40 minutes. V138 has not been timed.

## Entry points

From the repository root, offline verification (the default) opens no USB:

```sh
.build/picocalc-apps-arm-venv/bin/python .build/m0-v138-execution-20261023/run-math.py
```

After the approved transaction has installed/read back the exact image,
captured raw cold/crash/reset evidence and established command-mode idle
state at125MHz, its owner invokes `steps[0]` (matrix) and then `steps[1]`
(the explicit executable public-pow canary). `{port}` is
resolved by UID by that owner; no stale port is assumed. The command reads
`{output}/candidate-readback.bin` and writes into `{output}/math`.

An existing port can be reused by importing run-math.py and calling:

```python
run(port, uid="E6657CD423721C35", output=output / "math",
    verified_flash=output / "candidate-readback.bin",
    stop_file=output / "STOP-MATH")
```

Create STOP-MATH to cancel between completed chunks. Successful/cancelled
runs remove only the private SD directory `/MK61S-M0-V138-20261023` and
compare calculator observables before/after. Device failure saves raw
status/crash/identity/transcript and performs no cleanup/retry/reset/keys;
the parent transaction must restore in finally. `progress.json` and
`checkpoint.json` are atomically updated. Raw .bin/.guard.bin precede every
decoded result/checkpoint. Resume is explicit and hash-checked.
The SD root listing is parsed with row/count checks. File and directory
names are compared with casefold before creation, and root/dot/dotdot or
unexpected mutation paths are rejected. The parent must apply the same
collision guard before starting its transaction.

PASS means this finite execution completed with exact owned results and
preserved observables. The117 rows report any measured speed deficit;
PASS does not imply every row is faster. The 1,024-bit general-pow trap,
all-input guarantees, platform acceptance and production promotion remain
open work.

## Offline evidence and rebuilding

`app-self-test/result.json` covers the exact LTO APP ELF on all13 typed ABI
kinds, the original fixture's positive/error reporting, and five negative
guard tests. Timer, storage, UI, clock and XIP counters are mocked; actual
V138/reference numerical bodies execute. This is not a physical benchmark.
runner-self-test/result.json separately checks both executable stages,
cooperative cancellation/resume, failure evidence without recovery, FAT
path guards and rejection of modified helpers before import, using mock
ports only. The final physical receipts are still required.

To reconstruct the package before freezing, the recorded local dependencies
must exist: run prepare.py, make-canaries.py, layout-proof.py, coverage.py,
app-self-test.py with its recorded arguments, and finally freeze.py. Build
and test outputs must use a new private work directory when preserving this
frozen packet. No script here flashes firmware. The only serial-opening
branch is run-math.py with explicit --execute; USB ownership is required.
