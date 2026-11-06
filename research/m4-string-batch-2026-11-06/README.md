# Four Classic M4 string replacements, 2026-11-06

Status: implemented and compiled, functional tests and hardware timing NOT RUN.
The grouped package has also been compiled with --build-only (no ARM execution).
This is the candidate branch `feature/m4-string-batch-20261106`, based on
43eea5d82875a61cc9a729c4ccc2332eb49d73c8. The user requested all four replacements
before a single grouped validation pass. Main and the device image have not
been changed by this preparation.

| Function | Byte2 / default byte4 | Contract |
| --- | ---: | --- |
| strnlen | 34 / 54 bytes | Read up to n bytes, stop on first NUL; n0 reads nothing |
| strcpy | 26 / 46 bytes | Copy through NUL, return original destination |
| strncpy | 90 / 126 bytes | Write exactly n bytes, including zero padding; n0 touches nothing |
| strncat | 60 / 98 bytes | Preserve prefix, append at most n bytes and terminate, return original destination |

The functions use byte source loads with a check before each next byte. No
prefix/word source overread is introduced. strncat also returns immediately
when n0, with neither buffer touched. strncpy zero padding uses aligned 32-bit
stores only when four destination bytes remain; peel/tail writes are bounded.
All four kernels use caller-clobbered registers, no stack and no helper calls.

`MK61_M4_STRING_BATCH_UNROLL` selects 2 or 4 (default4) for the entire comparison
set. `MK61_M4_STRING_BATCH_DISABLE=1` compiles the original C controls. GNU
Cortex-M4 F411 uses the candidate bodies in this branch; F401, M0 and Clang
retain the C fallbacks. The SDK and its runtime26 ABI are unchanged. The
existing shared runtime slot21 reaches the replacement strncat; the other three
functions do not acquire new runtime slots. Standalone libc bodies remain
separate controls for the later comparison.

Full F411 normal-profile link succeeded with all four byte4 replacements:
400460 bytes, free Flash123828 >=16384; globals22024, maximum stack frame1928
<=5120. The image is unsealed, has not been installed and is not a measured
winner. COMPILE-ONLY.json records actual function sizes and hashes. Build
artifacts are in the primary checkout's `.build/m4-string-batch-20261106/`.

The grouped runner `tests/m4_string_batch_self_test.py` is intended to exercise
all four functions, both unroll widths, exact read/write bounds and padding,
all16 alignments, SRAM/Flash source, ABI, F401/M0 controls and the real
runtime26 slot21. Its `--build-only` mode compiles the complete set without
running ARM. The default mode is the later single HOST semantic pass. Use a
fresh `--output` directory and the pinned GNU Arm14.2.1 `--toolchain-bin`.
Guarded Unicorn execution must use `tests/unicorn_runtime.py::Uc` outside the
Darwin sandbox. HOST time is never hardware evidence.

TEST-PLAN.json records the subsequent single Classic campaign across all four
functions, controls, short/long strings and data/code placements. No physical
operator or grant is created by this change. Hardware execution will require
fresh image/runtime/timer/context binding and a coordinator window; retain all
raw groups and the first fault without retries. Winners are selected per
function from the complete regression map before main integration.
