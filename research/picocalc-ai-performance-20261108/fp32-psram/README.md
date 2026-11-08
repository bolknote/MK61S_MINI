# Exact FP32 group arithmetic and faster AI PSRAM reads

The retained firmware **048A0B3E / 597DDC06** measured **0.606646 and0.605948
seconds/token at270 MHz**, versus the requested0.714 target: **15.04–15.13%
less time**, about1.178× throughput. This is a short2-prefill/2-decode,
2-pass result on the frozen2093896-byte Q4 model, full classifier, two cores.
It is not a long-context latency measurement. No hardware baseline was rerun.

Tokens and linear checksums match the archived reference in both passes.
Read-divider telemetry confirms461/256, corresponding to about24.99MHz QPI
SCK at270MHz CPU. The separate5-second private PSRAM stress completed16346
pattern checks with no error; its time is outside timed decode. There were
no I2C errors or LCD-freeze violations. Both runs finished at125MHz in
CALCULATOR/CLOSED/NONE with CDC and the board lease closed. The final image
was retained; STM32 BIOS, Spectrum SD and ROMCACHE were not written.

## Changes

The INT8/Q4 kernel now scales each group's exact integer dot product using
specialized binary32 multiply/add for normal operands. The implementation
uses32-bit mantissa operations, preserves separate round-to-nearest-even
multiplication and addition, and falls back to the original EABI operators
for subnormals, nonfinite operands or boundary exponents. There is no fused
operation, reduction reordering, approximate activation or new quantization.
The addition helper has a bounded flash slot at0x101b5000. The original
model and attention slots and the ROMCACHE boundary remain guarded.

The first physical arithmetic-only result was0.7083255/0.7083175s/token,
less than1% faster overall. Its matmul time fell, but DMA wait grew:
weights had become the bottleneck. Contrary to an initial interpretation,
`wait_us` measures pending PSRAM read completion, not the core1 join.

Only QPI **reads at the qualified270MHz AI profile** then change PIO divider
from692 to461. SPI, writes,125/200MHz and Spectrum behavior retain their
normal divider. Every16-byte transaction still runs autonomously with the
same bounded RX FIFO and CE# handling. No transfer buffers, workspace, static
RAM, model, vocabulary or KV dimensions were enlarged. Static RAM120360,
heap109016 bytes, and the minimum108544-byte audio budget are unchanged.

The four existing improvements remain: ordinary chat uses the fast two-core
INT8 configuration; the64/128/256 diagnostic remains available; Q/K/V and
gate/up reuse activation preparation; paired query heads share KV reads.
The benchmark and buffer stress do not establish long-duration or all-unit
hardware stability, or a new long-context throughput result.

## Validation and evidence

- ASan/UBSan:68 full-logit comparisons,512-position exact KV;23 gathered
  full-logit comparisons,256-position KV,92881 joined batches, cancellation,
  refusal, partial I/O failure, numeric failure and worker/buffer guards.
- Exact arithmetic versus the production M0 EABI:8722880 operand pairs,
  including signed zero, subnormals, nonfinite values, exponent boundaries,
  rounding ties and cancellation. NaNs are compared as NaNs on HOST; actual
  ARM comparisons preserve exact bits including special values.
- Actual ARMv6-M execution:1536 scalar operand pairs and complete compiled
  INT8/Q4 kernels produce identical output bits. Instruction counts in
  `arm-profile.json` and `linear-profile.json` are not RP2040 cycle timings;
  ROM intrinsics are functional models and bus contention is not emulated.
- Eight published Russian INT8 SPEC fixtures preserve generated tokens,
  compiled programs and core results. See `spec-tests.log`.
- Production PIO tests use finite FIFOs and deliberately stalled TX/RX DMA;
  the proposed read clock retains a bounded CE# pulse below4us. The unchanged
  SPI program is checked separately. The physical5-second private-buffer
  test and all-model archived checksums exercise the actual faster path.

Each physical variant directory contains unmodified device JSON, its sealed
firmware manifest and hashes of relevant compiled sources. Both variants
preserve the newer Spectrum BB1B90AF platform rather than flashing the old
D1752771 baseline. RAM-placement and pre-rebase arithmetic prototypes were
HOST-only and were not flashed. The source commit includes only the qualified AI changes, tests and this
report; other agents retain their Spectrum/cold/clock work. Its source pins
identify the tested combined image; the partial commit alone is not claimed
to reproduce all unrelated changes in that firmware.

PSRAM timing reference: manufacturer APS6404L datasheet, timing table23:
[AP Memory APS6404L-SQH rev3.6](https://www.mouser.com/datasheet/2/1127/APM_PSRAM_QSPI_APS6404L_SQH_v3_6_PKG-1954912.pdf).
The test establishes behavior on this board; it does not identify a specific
package solely from the shared manufacturer/die identification bytes.
