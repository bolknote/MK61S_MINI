# RP2040 SIO interpolators for LUT8 — 2026-11-12

## Result

The SIO implementation did not deliver a meaningful advantage over a packed
CPU implementation. Both were faster than the resident matrix routine, but
that gain is not evidence that the interpolator helps.

Measured on PicoCalc RP2040, **270 MHz, both M0+ cores**, using real frozen Q4
weights and INT8 activations. For the 16 cases with a 28 × 128 matrix tile:

| Implementation | Median time, µs | Time saved vs resident |
| --- | ---: | ---: |
| Current resident hybrid LUT8 | 161.0000 | — |
| Existing scalar dot, new row-major wrapper | 118.3125 | 26.51% |
| Existing scalar dot, new group-major wrapper | 121.4375 | 24.66% |
| Packed CPU ASM, row-major | **111.1250** | **31.05%** |
| Packed CPU ASM, group-major | 112.1250 | 30.43% |
| SIO ASM, row-major | 113.9375 | 29.29% |
| SIO ASM, group-major | 111.6250 | 30.78% |

Times are medians of per-case medians. Each case has seven samples, each the
elapsed time of eight repetitions divided by eight. Percentages use the median
of *paired per-case ratios*, so they need not equal a ratio of aggregate times.
SIO group-major took 0.34% more time than packed CPU row-major by the same paired
calculation. Treat those two implementations as effectively tied in this test.

**This measures SRAM matrix tiles, not seconds per token.** LUT preparation is
shared and outside the timed region. PSRAM reads, attention, the other matrix
width, sampling and the rest of the harness are not included. No production
kernel, model, quantization or firmware was changed by this experiment.

## What was tested

- Twenty 128-column cases, with 28- and 16-row tiles; Q projection, FFN gate,
  and classifier beginning/middle/end; activation positions 0 and 3.
- Four 384-column cases using the unchanged resident direct kernel as controls.
- Each available implementation is checked with one core and two cores before
  timing; all timed samples require actual two-core worker submission.
- Variant order rotates across cases and rounds. Worker dispatch/join is timed
  identically. There is no timed one-core fallback.
- SIO save, configuration, table-base writes and restore are included in its
  timed matrix call. Both interpolators are saved independently on each core.
- Every timed output is compared bit for bit with the frozen expected FP32
  output, not merely against another variant's checksum.

All 24 cases passed. Separate ARM qualification passed 803 integer-dot cases
(1,606 checks) and 288 real whole/split matrix checks. The numerical tests also
check callee-saved registers, bounded stack use, worker refusal, malformed input
and restoration of interpolator state. Emulator instruction counts were not
used as timing measurements.

## Why the CPU version is promising

`packed_dot32` loads four plane-index bytes as one word, extracts four even
halfword offsets, and combines the four planes in reverse Horner order. It
returns exactly the same integer dot product and uses the existing weight
layout and INT16 subset tables. SIO still requires stores to its accumulators,
address reads, actual LUT loads and per-matrix state management; it did not
improve on the CPU alternative here.

The large resident-to-candidate difference is **not all a dot-kernel gain**:
`scalar_row` keeps the resident scalar dot function and still saves 26.51%.
Disassembly identifies additional differences in the surrounding arithmetic:

- Resident `half_scaled_q4_dot` calls the firmware's generic `__aeabi_i2f`
  through an SRAM-to-Flash veneer; that implementation delegates to the generic
  64-bit `m0_eabi::Binary<23,8>::from_integer` path. The private APP links its
  libgcc conversion routine in SRAM.
- Resident `std::isfinite` emits calls to generic `__aeabi_fcmpun` and
  `__aeabi_fcmpgt`. The APP checks the exponent bits directly.
- The APP's wrapper is specialized and compiled at O3. Both wrappers call the
  **same resident** `mk61ai::math::add` and `mk61ai::math::mul`, preserving group
  reduction order.

These observations explain why the wrapper deserves further work; this test
does not separately attribute time to conversion, finite checks, compiler
specialization or SRAM placement. Do not call the entire 31% gain an ASM or SIO
gain, and do not project it directly onto full inference. Production adoption
requires keeping validation/error handling and a full-token measurement with
the same model and current best settings.

## Evidence and device closure

- Machine-readable summary: `RESULTS.json` next to this file.
- Raw report: `.build/mk61ai/interp-lut8-20261112/hardware-001/results.json`.
- Raw binary: the same directory's `INTERP.BIN`.
- Run receipt and final status: `receipt.json` and `final-status.txt` there.
- Relevant actual ARM disassembly:
  `.build/mk61ai/interp-lut8-20261112/analysis-disassembly.txt`.
- Exact authorized package:
  `.build/mk61ai/interp-lut8-20261112/HARDWARE-PACKAGE.json`, SHA256
  `1a65a2cd75069262ceb530050f7650dc8a8a45d4278748eb40f55002dc9fc60f`.
- Resident build BC3E68F9 / AE970EF0, ELF SHA256
  `fcff572814c4f74ebe82c2fb690295d501240bf3f79f1bff90b84f1e27a6669e`.

One APP-only physical run was made after the coordinator's explicit handoff.
Both interpolator states, 125 MHz and rendering were restored; workspace was
released; only `/Apps/INTERP-20261112-001` was removed. Final UI was
CALCULATOR/CLOSED/NONE; CDC and the device lease were closed. BOOTS stayed 23;
settings, RTC, keyboard and I2C/error counters were unchanged. The pre-existing
retained crash record was preserved. No resident Flash or M3 writes occurred.

## Tools

`prepare.py` builds the private APP against an exact resident ELF and decodes
the raw report. `arm_test.py` qualifies the compiled kernels with the local
Unicorn runtime. `run_hardware.py` defaults to a host-only pinned-artifact check;
physical execution additionally requires a fresh coordinator handoff file.
The old handoff is consumed evidence, not permission for another run.
