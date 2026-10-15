# ZX0 word and SIMD32 prototypes

Historical SRAM experiment. Production integration and resident Flash
qualification are described in [ZX0-FLASH.md](ZX0-FLASH.md).

These experiments keep the ZX0 v2 format and production firmware unchanged.
`prepare_zx0_prototypes.py` freezes private scalar, word and DSP copies of the
current codec. The scalar copy is also compared with production in host tests.
The manifest records the source commit and hashes; generated files belong in
the selected output directory, not in `code/`.

The candidates are:

* **LZ copy:** bounded, byte-aligned 32-bit loads/stores. Offsets 1 and 2 build
  a repeating word; offset 3 rotates the three-byte period after each store.
  Larger offsets load and store one word at a time. Loading four words before
  storing them would break offsets 4..15. Neither ordinary `memcpy` nor
  `memmove` generally implements the required growing-dictionary semantics.
* **Match length:** an immediate first-byte mismatch path, then four-byte XOR
  comparisons and a trailing-zero count to locate the first differing byte.
* **Bounded-optimal LCP table:** compare four candidate bytes and update four
  16-bit lengths per block. The DSP variant uses `USUB8`/`SEL`, `UADD16`, and
  `USUB16`/`SEL` for masks, increments and lane maxima. The word variant uses
  ordinary integer operations. This relies on the existing encoder limit of
  8192 input bytes; it is not a general 16-bit saturating counter operation.

All word accesses require little-endian normal memory and stay inside the
original spans. A short tail remains scalar. `decode_range`, `StreamDecoder`,
literal callbacks, CRC, BCJ and the codec format are unchanged. DSP differs
from word only in the encoder LCP update; there is no separate DSP decoder.

The `zx0_register_candidate.hpp` follow-up keeps short matches below eight
bytes inline and returns a by-value cursor from the larger copy helper.
The first word prototype made the decoder cursor addressable on the stack
under GCC -Os, adding a load/store for each literal. The follow-up isolates
this calling-convention effect; it is built and measured separately.

## Verification

```
bash tests/experimental/run_zx0_candidate_tests.sh [existing.APP ...]
```

This runs ASan/UBSan differential tests, protected-page tails, all four byte
alignments, overlapping LZ periods, every short tail, random malformed streams,
truncated input/callback failures, output limits, encoder sink failures and
byte-identical full streams in both encoder modes. Optional actual APP streams
are decoded by all variants and checked against their original image CRC after
the existing reverse BCJ filter. Both historical ABI 3 and current ABI 6
containers are accepted as input data; neither is executed by this test.

`run_zx0_candidate_arm_tests.py` additionally executes the actual GCC Cortex-M4
word/DSP kernels in Unicorn, with exact memory read/write bounds and ABI checks.
It requires the existing Python Unicorn package and ARM GCC. Its report is an
ISA correctness check, **not a device speed measurement**.

## Hardware APPs

```
python3 tests/experimental/build_zx0_prototypes.py \
  --output-dir tmp/zx0-prototypes \
  --arm-toolchain-bin /path/to/arm-gcc/bin \
  --image /path/to/uncompressed/APP.bin
```

`ZX0KERN.APP` contains all matched kernel variants, with copies up to 512 bytes,
offsets 1..256, immediate/late mismatches and short/full LCP rows.
`ZX0CODEC.APP` contains full scalar/word/DSP encoders and scalar/word decoders.
It uses 4..512-byte constant, two-byte, three-byte, random, BASIC-source and
actual ARM-image fragments. The manifest freezes the two corpus prefixes.
These are complete codec calls on bounded fragments, not whole APP-loader or
filesystem benchmarks. File reading, reporting and fixture preparation happen
outside timed intervals. Each result uses seven DWT batches; variant order is
rotated, and all four byte alignments are checked.

The builder checks the exact native encoder corpus under ASan/UBSan before
creating the codec APP. Greedy plans use `3*n+64` bytes of scratch, below the
bounded-optimal threshold for these cases. The original fixed 512-byte scratch
legitimately rejected the 512-byte BASIC fixture in production as well as the
prototypes; that interrupted run is retained as incomplete. `--codec-scope
encode-focus` builds a shorter follow-up on real source/image fragments,
random input and a three-byte period, after the broad kernel experiment.
`build_zx0_register_prototype.py` builds a separate three-decoder comparison.

```
python3 tests/experimental/build_zx0_register_prototype.py \
  --output-dir tmp/zx0-register \
  --corpus-manifest tmp/zx0-prototypes/manifest.json \
  --arm-toolchain-bin /path/to/arm-gcc/bin
```

It reruns the differential/sanitizer tests with the by-value copy helper,
including protected-page tails. `run_zx0_candidate_arm_tests.py --register-copy`
checks this helper's actual Cortex-M4 code as well. The third decoder is named
`register_word` in reports; it is not labelled as DSP.

After explicitly receiving the pinned Classic from the current hardware owner:

```
python3 tests/hil_zx0_prototypes.py \
  --port /dev/cu.usbmodem2068336B47311 \
  --manifest tmp/zx0-prototypes/manifest.json \
  --output-dir tmp/zx0-prototypes/hil --runs 3
```

Use `--only ZX0CODEC` with a focused codec manifest to avoid rerunning a
completed kernel matrix. Each invocation requires a fresh output directory.

The driver requires an empty calculator and disabled alarms for warm resets.
It refuses collisions with reserved files, uses independently checksum-verified
CDC reads, and verifies original file hashes, firmware CRC and calculator state
after removing its APPs, control file and reports. It never flashes firmware.
Preserve the successful raw reports and generated source/data manifest with
any published summary. A SRAM kernel speedup cannot by itself establish an
improvement in resident Flash, APP loading or NOR/USB throughput.

## Classic results, 2026-10-15

The kernel matrix completed three runs (5376 checked rows). The corrected
follow-up completed three runs of 30 complete decoder cases and ten encoder
cases (1440 checked rows). Each row has seven DWT samples; the figures below
use the median of the three run medians and cover all four byte alignments.
The inputs are frozen 4..512-byte fragments, not complete applications.

| Complete operation | Input | Speedup over scalar |
| --- | --- | --- |
| Register-cursor decoder | 512-byte periods 1/2/3 | 1.70–2.16× |
| Register-cursor decoder | 512-byte BASIC / ARM fragments | 1.002–1.005× |
| Register-cursor decoder | Random literals | approximately 1.00× |
| Bounded-optimal encoder, word | 512-byte BASIC / ARM / random | 1.019–1.026× |
| Bounded-optimal encoder, SIMD32 | 512-byte BASIC / ARM / random | 1.045–1.058× |
| Greedy encoder, word | 512-byte BASIC / ARM fragments | 1.043–1.046× |
| Bounded-optimal encoder, SIMD32 | 16 / 64-byte BASIC / ARM prefixes | 1.674× / 1.447–1.499× |

SIMD32 adds 2.6–3.2% over the word encoder on the 512-byte optimal cases.
Greedy never runs the SIMD LCP update; its improvement comes from word match
search. Its synthetic three-byte-period case reaches 1.261–1.264×.
The register decoder is about 0.2–0.7% slower on some 64/256-byte source
fragments, so the near-zero source/image improvement is not a general win.
The largest spread between the three run medians was 0.12% for decoder rows
and 0.22% for encoder rows.

The original word decoder's pointer spill is visible in both its assembly
and its 3–5% regressions on 512-byte literal/source/image cases in the matched
follow-up. Keeping the pointer in a register removes that regression.
The measured APP text symbols, excluding alignment padding, total 482 bytes
for the scalar decoder and 660 for the register variant; the corresponding
encoder totals are 2422 scalar, 2754 word and 2734 DSP. These are SRAM APP
code sizes, not a prediction of firmware Flash after resident LTO.

The preferred next candidate is the SIMD32 optimal encoder with word match
search. The decoder helps long matches, but a loader or resident-Flash test
is needed to establish practical benefit on complete APP streams. Production
code, the format, compression ratio and encoded bytes remain unchanged.

Evidence is recorded in `zx0_results.json`; raw follow-up data and the exact
driver snapshot are in `tmp/zx0-followup-20261015/`. The original runner
completed every measurement, then stopped on a garbled identity echo during
its final reconnect. A separate strict, echo-correlated session removed the
verified test files and confirmed all 44 original files, four directories,
calculator state, alarms and firmware CRC before closing CDC. The driver now
uses that correlated text session; an offline PTY check rejects an incorrect
profile/build and ignores a stale uncorrelated reply. It was not rerun on
the board after that transport-only change.
