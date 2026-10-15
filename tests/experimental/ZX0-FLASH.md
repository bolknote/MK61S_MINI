# Resident Flash ZX0 encoder qualification

The production change is `f72e21103`: bounded word match scans and a four-byte
LCP update with Cortex-M4 SIMD32. The 256-byte window and 8192-byte input limit
are checked against the private kernel contract. Packed counters cannot carry
between 16-bit lanes. Every load stays inside the original span, with scalar
short tails. Other targets retain the previous scalar implementation.

The decoder, format, token selection, workspace sizes, heap use and public API
are unchanged. Production callers of `prepare`/`emit` automatically use the new
encoder; qualification does not add exports or profiler hooks to the firmware.

## Local verification

* ASan/UBSan existing encoder suite in scalar and forced-word configurations.
* 2,842,601 differential/bounds checks against the frozen original encoder,
  including complete byte-identical streams, malformed inputs, protected-page
  tails, all alignments, both modes and the 8192-byte limit.
* Three actual APP streams decoded and checked against their original CRC.
* 8,876 Cortex-M4 kernel checks, with the integrated DSP implementation.
* 774 calls to actual control/candidate Flash ELF `prepare` and `emit`, checking
  complete streams, prepared plans, output failures, memory bounds and ABI.
  Largest stack access in that isolated complete-call matrix was 824 bytes.
* C6/C9 store, journal, staging, arena and workspace tests under ASan/UBSan.
* F401 product Classic V3 resource gate: 255404/262144 bytes, 6740-byte headroom.

The ISA tests establish correctness and do not measure device cycles.

## Matched images and APP

Normal release builds use the same source snapshot, flags, toolchain and
`SOURCE_DATE_EPOCH`. Only `code/zx0_encode.cpp` differs between the images;
the private header is present in both snapshots. The initial pair has:

| | Control | Candidate |
| --- | --- | --- |
| Firmware CRC | `97E53E38` | `7F477836` |
| Sealed bytes | 373420 | 373724 |
| `.data` / `.bss` | 1656 / 30168 | 1656 / 30168 |

This is a 304-byte Flash increase with unchanged static RAM. Snapshots and
sealed BIN/ELF pairs are in `.build/zx0-flash-20261015/firmware/`.

After RAM/MPU integration, a second normal matched build on `7cd70e188`
measured 374688 bytes (`9468F51D`) versus 374976 (`342D9231`): **288 bytes**
added, with identical `.data` 1656 and `.bss` 24856. Those snapshots are in
`integrated-firmware/`; the device timings below belong to the original pair.

One unchanged `ZX0FLASH.APP` selects the resident by its sealed 40-byte footer
and exact 32-byte prefixes of both functions. Every result reports that CRC.
Timed intervals call the actual Flash `prepare` and `emit` through their pinned
addresses; the original scalar SRAM encoder runs only outside the timer and
checks the whole encoded output and canaries. It is a complete codec call on
bounded fragments, not storage, USB or complete application loading.

The frozen corpus repeats the earlier SRAM experiment: ten encoder cases on
16/64/512-byte BASIC, ARM-image and random fragments, plus a three-byte period.
Both encoder modes and all four byte alignments are covered. Each row uses
seven DWT batches with a warm-up before each batch.

```
python3 tests/experimental/build_zx0_flash_firmware.py \
  --output-dir /path/to/experiment/firmware --variant control
python3 tests/experimental/build_zx0_flash_firmware.py \
  --output-dir /path/to/experiment/firmware --variant candidate
python3 tests/experimental/build_zx0_flash_app.py \
  --firmware-dir /path/to/experiment/firmware \
  --output-dir /path/to/experiment/app \
  --corpus-header tests/experimental/zx0_flash_corpus.hpp \
  --arm-toolchain-bin /path/to/arm-gcc/bin
```

`--base-ref` selects the common source commit, defaulting to the frozen
pre-change `6781f4a24`. Generated manifests record exact hashes and compiler
settings. Use a fresh output directory for each new image pair.

```
python3 tests/experimental/run_zx0_candidate_arm_tests.py \
  --production-encoder --output-dir /path/to/experiment/arm-kernels \
  --arm-toolchain-bin /path/to/arm-gcc/bin
python3 tests/experimental/run_zx0_flash_arm_tests.py \
  --manifest /path/to/experiment/app/manifest.json \
  --output-dir /path/to/experiment/arm-flash \
  --arm-toolchain-bin /path/to/arm-gcc/bin
```

## Hardware protocol

The physical matrix is control / candidate / control, with three launches per
phase. A single APP and corpus are reused. The driver independently verifies
the installed Flash CRC, all result rows, and each original file fingerprint.
Each phase removes its APP, control file and reports; the finalizer restores
the exact original recovery firmware and checks calculator state and alarms.

Run only after explicit transfer from the current Classic owner:

```
python3 tests/hil_zx0_flash.py \
  --port /dev/cu.usbmodem2068336B47311 \
  --manifest /path/to/experiment/app/manifest.json \
  --recovery-bin /path/to/exact-original/classic.bin \
  --output-dir /path/to/experiment/hil --runs 3
```

If a run is interrupted, `--cleanup-only` uses its existing `snapshot.json`,
checks the same recovery hash, and removes only verified owned files. It does
not claim measurement success. The saved recovery is not replaced by any test
or final candidate image. Final main integration is serialized with the other
agent's frozen mixed-cache qualification.

## Hardware results

**PASS:** 3 + 3 + 3 launches, 90 raw frames and 360 checked rows on Classic
F411 at 96 MHz. Every measured full stream matches the original scalar encoder.
The final artifact is `.build/zx0-flash-20261015/qualified-flash-report.json`;
`zx0_flash_results.json` records the complete provenance and phase paths.

| Full prepare + emit from Flash | Input | Speedup |
| --- | --- | --- |
| Bounded optimal | 512-byte BASIC | 1.101× |
| Bounded optimal | 512-byte ARM image | 1.118× |
| Bounded optimal | 512-byte random | 1.130× |
| Bounded optimal | 16-byte BASIC / ARM prefixes | 1.652–1.653× |
| Bounded optimal | 64-byte BASIC / ARM prefixes | 1.468–1.527× |
| Greedy, word match search | 512-byte BASIC / ARM | 1.017–1.018× |
| Greedy, word match search | 512-byte three-byte period | 1.161–1.170× |

Ranges cover all four byte alignments. Results use the median of six control
launch medians (A1 and A2) divided by the median of three candidate launches.
The largest repeated-control difference is below 0.001%. These numbers concern
CPU codec calls; they do not establish USB or storage throughput gains.

All original 44 files/four directories, registers, stack, program, history,
working directory and disabled alarm slots were checked after exact recovery
122A5FF9. CDC was closed before explicit transfer to the next hardware owner.

The first attempt stopped before writing firmware on a missing utility path.
A subsequent completed candidate measurement lost a final read-only status
reply; its outer recovery passed. Command spacing and safe read-only retries
were added, then a clean A/B/A was run. Its final A2 comparison caught only
terminal prompt trailing whitespace (`/>` versus `/> `). The comparator now
removes only trailing whitespace, preserving all register/program data, and
saves the actual after-state before asserting. A2 alone was repeated and fully
passed; A1/B measurements and firmware/APP bytes were unchanged. The raw failed
attempts remain available and are not silently relabelled as successful runs.

The implementation is in main as `12fba17e7`, after RAM/MPU integration
`7cd70e188`. The physical pair used the pre-change common base `6781f4a24`;
the same encoder files on the new base also passed a normal merged firmware
build and repeated ASan/UBSan encoder and C6/C9 tests. No source change was
made to the other agents' frozen diagnostic pairs.
