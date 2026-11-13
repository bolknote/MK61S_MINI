# Packed CPU LUT8 integration

The faster CPU implementation from the LUT8 experiment was built into PicoCalc
firmware `1BDB4385` and measured on the device on 13 November 2026. The four
production files and two test files in the working tree match the measured
build's source snapshot byte for byte.

## Implementation

- `mk61_ai_kernels.c`: the ARMv6-M LUT8 dot kernel loads four plane-index bytes
  per word and combines the planes in reverse Horner order. It preserves the
  existing Q4 layout, exact signed INT16 tables and integer result. The entry
  checks word alignment; unaligned public-API inputs use the portable scalar
  implementation in Flash. The usual aligned kernel remains in SRAM.
- `mk61_ai_half_product.hpp`: AI-local, correctly rounded INT32-to-FP32
  conversion avoids the firmware's generic 64-bit EABI packer. It normalizes
  and rounds with unsigned 32-bit arithmetic, including INT32_MIN and ties to
  even. One shared SRAM function avoids duplicating the body in both matrix
  kernels. The calculator's global arithmetic runtime is unchanged.
- `mk61_ai_linear.cpp`: finite checks inspect IEEE exponent bits, retaining
  format checks, buffer checks, NUMERIC errors and the rule that a failed row
  is not stored. Group scaling and FP32 reduction order remain unchanged.
- `mk61_ai_kernels.h`: corrects the obsolete comment describing LUT8 tables as
  unused by production; no API or structure layout changes.

Both cores continue sharing the same immutable prepared LUT. Ordinary chat's
fast clock, long-context support, activation reuse and KV sharing/batched reads
are retained. No model weights, quantization, tokenizer or model memory
allocation changed.

## Verification

- ASan/UBSan: 3,114,112 FP16 dot-scaling comparisons, covering all FP16 scales;
  2,031,933 exact INT32-to-FP32 comparisons across the signed range and rounding
  boundaries.
- Actual combined ARM/ROM ELF: 803 dot inputs × eight alignments = 6,424 exact
  checks, including all index bytes and signed INT8 extremes. The 4,818
  unaligned-weight calls demonstrably enter the scalar fallback; no unaligned
  weight word reads occur. Callee-saved registers and SP are checked.
- Twenty-four real frozen Q4 matrix tiles, both whole and split between cores:
  all 48 FP32 results match the frozen reference bit for bit. Eight nonfinite
  cases and eight invalid-format/buffer cases are rejected. Kernel call-chain
  maximum stack usage is 224 bytes against the 2 KiB core-1 stack.
- Full-model HOST regressions: 68 parallel full-logit comparisons; 23 hybrid
  prefetch full-logit comparisons; exact 512-position KV; activation reuse,
  shared KV and gathered/batched reads; refusal, cancellation, failed DMA and
  join/thaw cleanup. Presentation outputs/KV/checksums remain exact.
- The complete PicoCalc platform test runner passed against the combined
  source tree, including native chat, color hardware scroll, LCD, I/O, clocks,
  firmware/settings boundary and keyboard fault recovery.
- The **new combined ELF**, rather than relabeled old reports, passed ARM
  Spectrum NRZ, I2C lease/service and keyboard tests. All seven Spectrum-owned
  production files are byte-identical to its handed-off snapshot.

The first HOST prefetch invocation used a full-plane reference where that test
requires an unconverted nibble reference for its fallback assertions. Replacing
that test input with the losslessly recovered canonical model restored the
required precondition; the corrected complete test passed. Snapshot-only
platform runs also needed their shipped game/font assets copied before the
full platform test could run. Neither issue required a production behavior
change.

## Combined artifact

Build **1BDB4385**, firmware CRC **161FEF7E**.

| Artifact | SHA256 |
| --- | --- |
| ELF | `8abddafabe3734c70df962b6184fe6deb23c0791e405a0fc90884d6b097e502f` |
| BIN | `3bf80036a764ff5c4c52f66bd5949ed9ae1a6927d999d04be75855d62fa2a648` |
| UF2 | `a84828a4d80e852c6f4dfd881dc75db08575a4f0e1bf63528fa43a46a61aca2c` |

Artifacts are under `.build/mk61ai/packed-cpu-20261112/combined/firmware`.
Flash image: 1,793,244 bytes. Static SRAM: 120,516 bytes; heap capacity: 108,860
bytes. **AI adds zero static SRAM bytes** relative to Spectrum's sealed509
base. Existing linker boundaries and reserved stacks are unchanged.

`combined/source-proof.json` preserves the provenance of Spectrum's exact799
archived inputs and the six AI replacements; supplemental, unchanged build
dependencies are separately recorded. `combined/source-stable.json` confirms
that compiled inputs stayed unchanged through build and platform tests, with
exactly four production differences from sealed509. Source snapshots, handoff
files and prior packages were not rewritten.

The hardware run used the installed build and the two-core inference package
at `.build/mk61ai/packed-cpu-20261112/INFERENCE-DUAL-CORE-PACKAGE.json`, SHA256
`07968079c36dc9ff92f05c81b2967425da79fd72082c013172a63b9908f69869`.

## PicoCalc measurement on 13 November 2026

The benchmark used the same Q4 model, prefetch, display policy and two RP2040
cores at 270 MHz as the archived LUT8 run on firmware `C99DE0AF`. Each pass
prefills two tokens and decodes two. Times below are seconds per decoded token.

| Pass | Previous LUT8 | Packed CPU | Reduction |
| --- | ---: | ---: | ---: |
| 1 | 0.4123725 | 0.3982725 | 3.42% |
| 2 | 0.4285335 | 0.4143235 | 3.32% |
| Mean | 0.4204530 | 0.4062980 | 3.37% |

The second pass includes 32.220 ms of display work across two tokens and was
1.951 ms/token slower than the previous best. Subtracting the separately
measured display time gives 0.398076 and 0.398214 s/token for the two passes.
Both token sequences and all output checksums matched the frozen reference.
PSRAM passed 8,670 stress cycles over five seconds.

Across prefill and decode together, matrix work fell from about 616 to 392 ms
per pass. Waiting for prefetched weights grew from about 172 to 384 ms,
consistent with the cores reaching the DMA wait sooner. The output classifier
stayed near 202 ms per pair of decoded tokens.

Spectrum stopped its sound test on an NRZ framing error. The coordinator
released the installed firmware for the independent two-core inference test.
The report recorded zero M3 jobs. Afterward, the controller returned to 125 MHz,
removed its temporary files, released the USB connection and handed the board
to Memset.

Device report and receipt are in
`.build/mk61ai/packed-cpu-20261112/inference-dual-core-001/`.
