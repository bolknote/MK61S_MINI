# Exact matrix candidates for PicoCalc

These tests cover LUT8, skipping exact INT8 zeros, and certified greedy
classifier pruning. All code is private to the test suite. The production
dispatch, model, tokenizer, KV cache and firmware remain unchanged.
The reference is the actual retained **7C38C634 / 8A17554E** firmware at
270 MHz, with the same nibble-packed Q4 model used for the retained
0.4277315/0.442951 s/token result.

## Physical result: PASS

The corrected APP completed all24 real matrix cases on both M0+ cores at
270MHz. `hardware-005/MATHTEST.BIN` is the durable report; `summary.json`
contains the medians and complete per-case results are in
`hardware-005/results.json`. No new full-inference timing is claimed.

For comparable classifier tiles of28 rows by128 columns (eight fixtures):

| Method | Preparation, µs | Compute, µs | Total, µs |
| --- | ---: | ---: | ---: |
| Actual resident kernel | 1.875 | 208.375 | 210.250 |
| Full LUT8 | 189.562 | 140.438 | 329.875 |
| Bounded LUT8 | 2.000 | 328.250 | 330.375 |
| Skip exact zeros | 17.625 | 293.750 | 311.438 |
| Classifier halfway certificate | 10.562 | 230.250 | 240.938 |
| Certificate before final group | 10.500 | 191.812 | 202.312 |

Each column is the median across fixtures of the six-round median;
therefore the displayed prep and compute medians need not sum to total.
On all12 classifier fixtures, including the four16-row tail tiles, the last
certificate's median total ratio is0.9143. On just the comparable28-row tiles
it is0.9542; the benefit depends on the causal best score and rows skipped.

Full LUT8's compute kernel takes about32.5% less time. Preparing it again for
every tile loses: the table must be prepared **once per input vector and
shared read-only across all output tiles**. From the measured prep and compute
costs it breaks even at roughly78 output rows for128-wide input (8,200B of
tables), or90 rows for384-wide input (24,600B). Linear extrapolation predicts
arithmetic time ratios of0.875 for the128-row Q projection,0.738 for the384-row
FFN gate,0.913 for the128-row FFN down projection, and0.677 for the8192-row
classifier. These are explicitly arithmetic estimates from SRAM tiles:
integration must measure weight layout, DMA/KV interaction, SRAM cost and
complete tokens. Repacking to bit planes is lossless. No candidate has yet
replaced the production dispatch.

Bounded LUT8 and exact-zero skipping lose in these measurements. The last
classifier certificate is an exact small-memory alternative, but its current
compute kernel is slower than full LUT8 with reusable tables.

The run returned to125MHz/CLOSED/NONE and removed its own test directory;
CDC and the lease closed. BOOTS remained19, all protected counters stayed0,
and the pre-existing I2C/reset/keyboard error counters remained7/7/7. The old
crash record stayed available and was not cleared. Missing USB stage markers
coincided with deliberate disconnects; the durable report verifies both
clocks, restoration, completed two-core rounds and exact numerical checks.

`run-hardware-005.py` and its package are historical qualified controller
snapshots. Their frozen helper/build dependencies retain local paths in the
manifest. Rebuild the APP with the commands below and obtain a fresh shared
device handoff before preparing a new physical package; do not reuse grants.

## Completed HOST and ARM checks

The ASan/UBSan host suite intercepts actual production linear batches from
32 forward passes on four English/Russian prompts, without modifying the
model source. It checks the entire matrices, including all 8,192 classifier
rows. Matrix metadata, row offsets and copied weights/scales are verified
against the immutable model package before each comparison.

- 2,272 matrix calls and 28,576 tiles: **671,744 rows** compared bit for bit
  for direct integer dots, full LUT8, bounded LUT8 and skipping exact zeros.
- **262,144 classifier rows**: every cut position preserves greedy selection;
  requesting all logits disables pruning and returns bit-exact full logits.
- Synthetic tests cover zero density, INT8 extremes, signed FP16 scales,
  tiny activation scales, exact ties and earliest-token selection, nonfinite
  suffixes, corrupt norms, and exact integer square-root boundaries.
- The actual ARM/ROM code passes **288 probes on 24 real matrix tiles**, using
  both the scalar and actual two-core dispatch entrypoints. An ARM callback
  shim substitutes only mailbox scheduling, executing the real core1 callback
  inline; physical concurrency remains the device test's responsibility.
  It uses the resident SRAM linear kernel as reference, the same selected
  FP32 operations, real ROM3 and the exact production half-product body.
  CRC corruption and underestimated norms are rejected before computation.
  The emulator checks callee-saved registers, SP and permitted write ranges.
  The revised APP's largest numerical probe uses 408 bytes of stack. This
  measures the probe call chain; it excludes native service, worker and IRQ
  frames and is not a whole-application stack measurement.

`host-results.json` and `arm-results.json` contain the checks. The model SHA
and source pins are recorded in `host-source-pins.json` and the local package.

## Exactness of classifier certificates

For each 32-value group, store the immutable integer weight norm
`W2 = sum(qw[j]^2)` as a uint16; prepare `X2 = sum(qx[j]^2)` per input.
The integer dot magnitude is bounded by `ceil_sqrt(W2 * X2)`. The product is
at most 2^30, so the calculation fits uint32 and the square root is exact.
Both the square-root enclosure and its boundary transitions are tested.

The bound then follows the original FP32 computation: apply the same
rounded half-scale product and activation-scale product to positive bounds,
and execute each remaining FP32 addition in the original order, beginning
with the already computed prefix. Monotonic RNE therefore bounds the final
FP32 score directly; no guessed floating error tolerance is used. Nonfinite
bounds disable pruning, and equal scores preserve the earliest token ID.
Norms are validated against the actual immutable weight codes before use.

This optimization supports greedy selection. It never invents omitted
logits: a request for all logits uses the complete original computation.

## Calibration and memory costs

Only **9,138 of 372,736 INT8 values (2.45%)** were exactly zero, and none of
the 46,592 eight-value blocks was entirely zero. This limits the likely
benefit of the exact-zero candidate on this model.

The halfway classifier checkpoint rejected 6,980 rows (2.66%); the checkpoint
before the final group rejected 206,605 rows (78.81%). The latter skips only
one of four integer dot groups on those rows, **not 79% of classifier work**.
Bound computation, its rounded scaling/addition and metadata reads have a
cost that still needs physical measurement.

Full LUT8 needs 2,050 bytes per 32 activations: 8,200 bytes at width 128 or
24,600 bytes at width 384, shared read-only by both cores. Bounded LUT8 uses
one 2,050-byte table per core, rebuilding it for each group/tile. It preserves
each row's FP32 reduction order. The full variant prepares tables once per
matrix input; the bounded variant includes preparation inside its kernel.
The classifier norm sidecar adds 65,536 bytes for the 8,192 by 128 head.
Lossless offline bit-plane repacking keeps the Q4 weight byte count unchanged.

## Prepared physical benchmark

`MATHCAND.APP` compares the actual resident SRAM kernel with both LUT8 forms,
exact-zero skipping and the two certified classifier checkpoints. It validates
one-core and two-core output before timing. Timed work uses both M0+ cores
at 270 MHz, six rotated rounds and four repetitions. Preparation and compute
are recorded separately. A worker refusal fails the run rather than silently
turning it into a single-core measurement.

The data contains 24 real tiles from Q projection, FFN gate/down and the
beginning/middle/end of the classifier. Each classifier tile receives only
the best score from preceding rows, never an oracle score from future rows.
Full-logit fallback is tested before timing. Setup allocates a bounded SRAM
workspace, freezes LCD transfers, retains normal service between jobs, and
restores 125 MHz/releases all workspaces before writing the owned result.
Resident footer checks reject a mismatched firmware before pinned calls.

These are compute measurements on real SRAM tiles. SD fixture reads are
outside timed intervals. Sidecar I/O and whole-model DMA/KV interactions need
an integrated inference measurement if a candidate wins; the microbenchmark
must not be presented as a full-token speedup. No physical timing is claimed
until the device report is retrieved and validated.

## First physical attempt and revised package

`hardware-001` is **HOLD**, not a benchmark result: the device rebooted with
`BOOT_WATCHDOG=1`, BOOTS changed from 15 to16, and no `MATHTEST.BIN` survived.
The initial firmware remained 7C38C634 /8A17554E and returned to125MHz.
The controller removed only its new owned APP directory and closed CDC and
the lease; it did not reset, flash or replay the test. Post-reboot zero I2C
counters do not preserve or validate the earlier counters of2. Original
receipt and before/after snapshots are retained in the local build directory.

Inspection found a reachable infinite/reentrant display path in that private
test APP: it suspended `io_worker` frames directly while leaving the host's
`ai_frozen` flag false. Normal `service()` therefore ran
`NativeHost::pump -> display.flush -> PRESENT BUSY -> color_wait -> pump`.
That path agrees with a watchdog failure, but the exact stage of the failed
physical run cannot be established because the old APP had no stage markers.

The revised APP uses the existing `NativeHost::ai_render(false/true)` gate,
as the ordinary harness does. It suspends both host presentation and frame
submission. It writes `SETUP.BIN` at125MHz before freeze/PLL, emits stage1..7
and case markers, and services the host for500ms immediately after the clock
change. Timing excludes these diagnostic steps. Before writing the final
result it joins the worker, restores125MHz, opens the presentation gate and
releases its workspace. This private APP uses41,564 image/BSS bytes plus a
28,700-byte SRAM workspace; its image remains below the49,152-byte APP limit.

`HARDWARE-PACKAGE-002.json` and `run-hardware-002.py` pin this revision and its
new ARM qualification. The controller preserves serial bytes across clears
and reconnects, accepts only a fresh coordinator-supplied exact counter
baseline, and always treats a boot-counter change as failure. It cannot run
without an explicit unexpired package-specific handoff. No second physical
attempt was made while the device was assigned to Spectrum.

After a fresh handoff, `hardware-002` verified all24 cases on the two cores
and emitted `case=24/24 ok=1`, then `stage=6`. It did not reach stage7 or save
the final timings. The test contained a separate cleanup bug: `dispatch()`
had already consumed every submitted job through `join_compute()`, then
cleanup called that function again. The resident mailbox accepts join only
in DONE; a second call on IDLE waits forever. The unconditional final join
is removed. A shared test-only `ComputeLease` now calls native join only
for an accepted unconsumed submission. HOST regression exercises
DONE→join→IDLE, a second guarded join, scope cleanup and a declined submit.

The final boot counter was18 instead of16, with `CRASH=AVAILABLE` and
`BOOT_WATCHDOG=0`. A separate authorized read-only collection preserved the
crash record and all counters. Exact ELF decoding maps PC100DF58C to `_exit`
(`BKPT0`) and LR100DA589 to SDK `panic`, at uptime1163ms/state0. The retained
frame does not expose the original panic caller, so it does not explain
the intervening boot's panic. `hardware-002-hold.json` records this limit,
the stage6 proof, counter transition and pinned evidence. No speed claim is
made from the lost timing report. The revised numerical HOST/ARM tests pass.

Attempt003 then exposed an independent compiled-code failure. The saved
registers match APP base2001E450: LR2001FB65 follows the `memcpy` at linked
20001710, R1 equals relocated `original+57`, and R4 equals the resident service
callback1005FE31 plus one708-byte Job. GCC's final LTO tree contains
`__builtin_unreachable()` immediately after stage5; its invalid fallthrough
re-enters job setup after overwriting the job pointer with the callback.
This deletes the two-core dispatch and timing tail and ultimately tries to
use100600F5 as writable SRAM. An exact diagnostic relink reproduces the old
image byte for byte. Missing USB markers during the intentional disconnect
therefore did not establish that `ai_clock::begin` failed.

The test-only guard now stores addresses of local `noipa` adapters; those
adapters perform the pinned native calls directly. The final linked APP CFG
retains all stages1–7/60–63 and timed submit/join calls beyond validation
probes. ARM tests execute the actual guarded two-core path for every method
and full-logit mode, and verify a refused submit returns failure without an
idle join. A negative ARM replay of the retained exact003 ELF reproduces
destination100600F5 and LR2001FB65 before an invalid write. See
`cfg-results.json` and the `regression-003` fixture. Neither the production
firmware nor its compiler flags were changed.

## Reproduce

```sh
python3 tests/prepare_mk61_ai_math_candidates.py \
  --model .build/mk61ai/swar-v5/MODEL-NIBBLE.MKA \
  --resident-elf .build/mk61ai/math-choice-20261111/firmware-candidate/mk61s-picocalc-pico-h.elf \
  --output-dir .build/mk61ai/math-candidates-20261111
python3 tests/mk61_ai_math_candidates_arm_self_test.py \
  --package-dir .build/mk61ai/math-candidates-20261111
python3 tests/mk61_ai_math_candidates_cfg_self_test.py \
  --package-dir .build/mk61ai/math-candidates-20261111
```

Use an interpreter with Unicorn and an available MPFR installation for the
existing host tools. On macOS, the emulator host check may require normal
tool approval for `hw.cachelinesize`; it does not access the PicoCalc.
`--reuse-host` reuses the full-model test only if source and model hashes
still match the completed ASan/UBSan run.

The builder writes a pinned private APP, CRC-protected `MATHCASE.BIN`,
package metadata and per-case dimensions under the local build directory.
Physical execution uses a fresh owned APP directory and the shared device
handoff; no firmware, settings, model or STM32 writes are required.

```sh
python3 tests/prepare_mk61_ai_math_candidates.py \
  --decode-result /path/to/MATHTEST.BIN
```
