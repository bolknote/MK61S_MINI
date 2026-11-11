# Native hybrid LUT8

Measured native two-core inference at270MHz:

| Pass | Retained direct INT8 | Hybrid LUT8 | Less elapsed time |
| --- | --- | --- | --- |
|1|0.4277315 s/token|0.4123725 s/token|3.59%|
|2|0.442951 s/token|0.4285335 s/token|3.25%|

Mean elapsed time improved3.42%. Model/tokens/full checksums are unchanged.
Same Q4 model SHA256:
`67aae98d9ffbd332bbea6e9a7dde9ec003f8213b99d92c555b523c794256d01b`.
No historical run was repeated. Exactly one firmware flash and one full PERF
invocation produced the candidate results. FirmwareC99DE0AF/528F4874 remains
installed. The raw controller receipt is `MEASURED`: its stricter gate compared
both passes with the single fastest reference pass. That gate is false and is
preserved. Both corresponding passes improved; pass2 includes about31ms of
presentation per two decoded tokens in both reference and candidate.

The matmul timer fell19.1–19.2%, but uncovered DMA wait rose from66–67ms to
172ms across four forward calls. Faster arithmetic exposes weight reading;
these nested diagnostic timers must not be summed as independent wall times.

Initial loading took9.002s versus3.901s: lossless in-PSRAM conversion adds
startup work. Exporting the already prepared hybrid package avoids conversion;
the native idempotence test verifies the no-write path. The installed global
model is not rewritten by this experiment.

PSRAM stress:5s,9415 iterations, no byte/CRC/math errors.125MHz was restored.
Freeze/thaw9/9, I2Cerrors0, heap peak87268/108924B, stack peak25520/32768B.
BOOTS19→20 is the single planned flash reboot; the old retained crash is
preserved. All counters remain0→0 after boot. ROMCACHE bytes match before and
after the flash. Prior private PERF files were restored exactly, our temporary
APP folder removed, CALCULATOR/CLOSED/NONE reached, CDC/lease closed.

For128-column Q4 matrices, build four exact `mk61ai_lut8x32` tables once per
quantized input. Q/K/V and gate/up reuse these tables; both cores read the same
immutable tables while writing disjoint output rows.384-column down projections
retain direct INT8 arithmetic. The existing28-row tiles, DMA prefetch, KV gather,
parallel/shared attention, input reuse, normal-chat fast clock, frozen LCD and
Esc/pause remain enabled.

LUT entries are exact int16 subset sums. Integer dot products, group scales and
FP32 reduction order match the old INT8 kernel. This changes packing and how the
same arithmetic is computed; it does not retrain or requantize the model.

The native loader losslessly converts only its private PSRAM package before
binding workspace. The SD file is untouched. Model tensors/scales, tokenizer,
token IDs and RoPE are unchanged; payload/header CRCs reflect the new packing.
Read/write/cancel failures discard the private partial copy. Already converted
packages perform no writes. Read-only generic Model callers can retain the
original layout and direct kernel.

Memory: tables8200B, padded8208B; the old lookup reservation was6144B. Workspace
growth is2064B. New SRAM code uses768B; heap capacity108924B (minimum108544B).
Loader conversion uses a bounded1024B block plus16B group temporary on stack.
Cold conversion code lives in the existing AI diagnostic flash slot.

HOST qualification:

- ASan/UBSan: full old AI suite and native PicoCalc AI UI tests passed.
- Original nibble vs hybrid: all arithmetic modes/full logits; INT8 through all
  512 context positions and all2,621,440KV bytes match bit for bit.
-324631 DMA requests overlap joined worker jobs; cancellation, retry, read/DMA
  faults, worker refusal, numeric error, shared scratch and display thaw pass.
- Native conversion from nibble/full-plane/mixed packages exactly matches the
  independent Python conversion, including both CRCs; idempotence and fault
  handling pass.
- Final firmware ELF executed in ARM/ROM emulator:24 real model tiles, whole
  and split rows, bit-exact outputs. Kernel stack maximum216B. This is numerical
  and ABI qualification, not a device timing measurement.

Hybrid package SHA256:
`caa18a78aea45027d5e5857f1ab91d22c7790a802f39c6549243698508025798`;
same2093896B,61 tensors repacked. Offline conversion is optional:

```sh
python3 tools/apps/mk61ai/repack_model.py --input MODEL.MKA --output MODEL-HYBRID.MKA --layout hybrid
python3 tests/mk61_ai_repack_test.py MODEL.MKA
```

The global package had previously been SHA-checked as full-plane layout
`45ebc482d2247d36d386c9563becb89d3ca08868db66aad001afa977703b0166`.
Both this file and the retained nibble file convert byte-identically to the
same hybrid package in the native conversion test. Admission001 discovered
that the global model has since been replaced with a2160856-byte package;
it stopped before any flash or inference. Our files were removed and counters
preserved. Reviewed revision3 used the retained2093896-byte private model in
`/AI/HILV3-M3-9943AE8536E2`, with a fresh SHA check before flashing. Its existing
CFG/REF/JSON were backed up and restored, MODEL/M3LINE were never written.

Reproduce cross-layout inference using the existing prefetch self-test: compile
`mk61_ai_model.cpp`, `mk61_ai_linear.cpp`, `mk61_ai_tokenizer.cpp`,
`mk61_ai_kernels.c` and `tests/mk61_ai_prefetch_self_test.cpp` with the same flags
as `tests/run_mk61_ai_tests.sh`; pass original and hybrid package paths as the
two arguments. `tests/mk61_ai_repack_self_test.cpp` takes original, hybrid and
full-plane paths. `tests/mk61_ai_lut8_native_arm_self_test.py` takes the final
firmware ELF and the archived math-candidate `MATHCASE.BIN`.

Working artifacts and the hash-pinned hardware controller are under
`.build/mk61ai/lut8-hybrid-20261111/`. Archived evidence is in
`hardware-002/`, with the strict raw receipt and the derived `summary.json`.
`reference-performance.json` is the retained earlier result, not a rerun.
