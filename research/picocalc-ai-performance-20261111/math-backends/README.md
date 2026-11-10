# AI math on RP2040 at 270 MHz

The retained build **7C38C634 / 8A17554E** decoded at **0.4277315** and
**0.442951 s/token**, 28.2% less time on average than the archived
[0.606 s/token reference](../../picocalc-ai-performance-20261108/fp32-psram/README.md).
Both passes use the same 2,093,896-byte Q4 model, two M0+ cores, INT8
activations, 28-row tiles and two prefill plus two timed decode tokens.
No historical control was rerun. The two decode intervals contain about
320 ms/token in the layers and 107 ms/token in the classifier; display
presentation accounts for the difference between passes. This is a short
context throughput measurement.

Private PSRAM stress passed 9,479 iterations in 5 seconds before inference.
The benchmark reproduced the archived greedy tokens and independently
computed new FP32 checksums. Clock, display and input returned cleanly to
stock operation. The ROMCACHE checksum is identical before and after flash,
and the three preexisting private diagnostic files were restored.
`inference-timings.json` contains the on-device counters and `result.json`
records the comparison and final state.

The scalar benchmark ran on the PicoCalc at 270 MHz, with six rotated rounds
of 2048 calls per variant. It times ordinary FP32 inputs and subtracts the
same call-loop control. Precision was checked against 192 MPFR cases per
operation, including zeros, subnormals, infinities, NaNs and rounding edges.
The table shows median cycles per call. Parentheses give MPFR mismatches;
blank counts mean zero mismatches. Bold is the fastest qualifying variant.

| FP32 operation | Previous firmware | Project routine | ROM FP32 raw | ROM FP32 guarded | GCC / newlib local | ROM FP64 with conversion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| add | 425.5 | 125.4 | 84.5 (15) | **122.7** | 130.8 | 252.1 (12) |
| subtract | 427.1 | 127.7 | 87.2 (18) | **125.1** | 133.3 | 257.1 (12) |
| multiply | 432.0 | 135.6 | 67.4 (27) | **105.5** | 162.9 | 319.3 (15) |
| divide | 1159.5 | 1170.1 | 80.4 (27) | **118.4** | 457.6 | 351.4 (12) |
| sqrt | 1443.6 | **80.5** | 72.3 (35) | 93.3 | 827.0 | 287.9 (29) |
| exp | 11292.9 (18) | **822.7** | 533.5 (36) | 551.0 (26) | 3601.8 (18) | 926.5 (4) |
| round | **36.0** | 45.2 | — | 45.0 | 45.2 | — |

The guarded Qfplib route serves `+`, `−`, `×`, and `÷` on normal FP32 operands
and results. The existing IEEE path handles the rest. The project `sqrtf`
and `exp` (with the latter narrowed to FP32) serve square root and exponential.
Rounding keeps the previous firmware `roundf`. The GCC/newlib column tests
local GCC helpers for the elementary operators and local libm for functions.
The changes are confined to AI; the global runtime and calculator are untouched.
Integer Q4 dot products and weight and KV formats are unchanged.

`arm-mpfr.json` covers all 1,344 cases on the built ARM image using the
captured RP2040 ROM3. The full-model check used actual ARM exponentials and
reproduced the old hardware checksums. The new exponential is more accurate
on the scalar corpus, so the new image has separate expected bit checksums.
All 52 compared greedy tokens matched, and the new/old perplexity ratio was
0.99903 over 48 targets. Eight additional Russian SPEC fixtures completed
with the expected emulator results; the PicoCalc native host suite passed
with the real model under ASan and UBSan. These results describe the tested
sample, not a guarantee for all prompts.

The usual 270 MHz chat path, long context diagnostics, activation reuse and
batched KV reads remain available. PSRAM stays at its qualified ~25 MHz QPI
read clock. Build opt-out: `--no-ai-fast-math`; the `--compiler-runtime`
control also uses the original math route. Raw timings and details for each
variant are in `scalar-timings.json`.

The APP fixture is `tests/mk61_ai_math_benchmark.cpp`. Generated vectors, the
pinned measurement package and the sealed firmware are retained locally under
`.build/mk61ai/math-choice-20261111/`.
