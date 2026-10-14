# Cortex-M4 EABI arithmetic

The native resident no longer takes object files from `libgcc.a`. It provides
exactly the binary64 and unsigned division helpers needed by the resident and
its published System APP runtime table. The 26 runtime slots and their order
are unchanged. Binary64 remains 53-bit, nearest-even, including gradual
underflow, signed zeros, infinities and NaNs. No floating-point exception flags
or heap state are modified by the new integer arithmetic.

This phase improves performance at a cost of **704 Flash bytes per board**;
static RAM is unchanged. The following phase removes the retained malloc and
newlib state. Removing an archive name alone does not save memory: the old
GCC helpers were already architecture-specific Thumb-2 assembly.

| Board | Before Flash | After Flash | Static RAM | CRC |
|---|---:|---:|---:|---|
| Classic V3 UC1609 | 360632 | 361336 | 28560 | 71C47A53 |
| mini V3 LCD1602 A00 | 333120 | 333824 | 27224 | 415FE864 |

## Implementation and attribution

`native_eabi_fixed.S` preserves the fast ARM algorithms from GCC 14.2.0
`libgcc/config/arm/{lib1funcs,ieee754-df}.S`, specialized to little-endian
Cortex-M4 / Thumb-2. These functions are **derived from GCC, not newly authored**.
The copyright notices, GPL-3.0-or-later license and GCC Runtime Library Exception
3.1 are preserved; the exception text is `code/GCC_RUNTIME_EXCEPTION.txt`.
Other architecture configurations and the old quotient-bit division are absent.
The chosen input file hashes are recorded in the measurement JSON. Source:
[GCC 14.2.0](https://github.com/gcc-mirror/gcc/tree/releases/gcc-14.2.0/libgcc/config/arm).

`native_eabi.cpp` supplies independently implemented integer algorithms for:

- binary64 division: a native UDIV reciprocal seed, two Q63 Newton iterations,
  and exact 106-bit product/remainder correction before nearest-even rounding;
- subnormal results rounded directly, avoiding double rounding;
- unsigned 64-bit divmod using 32-bit UDIV and radix-65536 quotient digits;
- comparisons and double-to-64-bit integer conversion.

`native_eabi_arm.S` handles the special EABI divmod return (quotient in R0:R1,
remainder in R2:R3) and exact exponent scaling for normal powers of two. It
passes rare subnormal scaling to a separate C++ function, keeping packing
branches out of the reciprocal's live register state. No float approximation
is used. UMULL provides exact integer products, not a SIMD precision reduction.

C++ arithmetic compiled without LTO keeps its typed `pcs("aapcs")` signatures
separate from the stable runtime table's erased function-pointer declarations.
An explicit `MK61_USE_NATIVE_EABI=0` control restores toolchain arithmetic.
Unused helpers and constants are still removed by section GC.

## Measurements

One identical ordinary APP executes 1024 calls in each of nine DWT batches.
Median batches subtract an identity call with the same soft EABI, volatile
operands and output. The APP is in SRAM; resident helpers are in Flash.
Both images use 96 MHz, the same MCU, release configuration and toolchain.
Numbers below are cycles per call; see the JSON for all 48 cases and raw times.

| Operation/input | GCC baseline | Native |
|---|---:|---:|
| add 0.7, 1.3 | 90.083 | 90.077 |
| subtract 0.7, 1.3 | 91.088 | 90.089 |
| multiply 0.7, 1.3 | 62.067 | 62.068 |
| divide 0.7, 1.3 | 613.391 | 352.281 |
| divide 1.3, 0.7 | 614.390 | 354.279 |
| divide 1, 2 | 30.080 | 29.070 |
| divide smallest subnormal, 1 | 451.31 | 147.16 |

The suite also records tradeoffs: negative zero / 2 is 47.08 -> 67.09 cycles;
minimum normal / minimum subnormal is 419.30 -> 427.34. These are not silently
excluded. Full function timings on both boards improved most for tan, asin,
acos, atan and logarithms; integer-kernel sin/cos/sqrt stay almost unchanged.
For example Classic atan(0.7) is about 22.59 -> 20.34 us, and ln(1.3) about
26.43 -> 23.89 us. Full raw nine-batch measurements are included.

The linked [SEGGER table](https://www.segger.com/products/development-tools/runtime-library/technology/floating-point-library/#explicit-function-performance)
publishes `sinf/cosf/tanf/expf/logf` timings, not matching binary64 transcendental
results. Its separate implicit-function table gives averages for double helpers
(e.g. division 134 cycles), using another MCU, RAM execution and an unspecified
input distribution. Our per-input Flash measurement is not a controlled speed
ratio against that average. No licensed emFloat binary was executed here.
The original libm chapter records matched 51-input GNU/owned RAM measurements.

## Qualification and reproduction

- 140338659 independent host checks with ASan/UBSan, including random operands,
  cancellation/rounding/exponent boundaries, valid casts, u64 division and exact
  power-of-two scaling. The oracle is host IEEE arithmetic and integer division.
- 71086 actual ARM calls per board: bit equality for finite arithmetic/casts,
  NaN class and recorded GCC boundary behavior; raw soft-EABI GPR arguments,
  callee-saved integer/VFP registers, SP/FPSCR and stack-only writes.
- Both production ELFs pass 1897 independent high-precision libm vectors and
  54 IEEE cases; three ordinary service APPs execute at three load addresses.
- All 16 F411 and 9 F401 variants build. The link-map gate rejects included
  libgcc/libm/libstdc++ archive members. F401 product CORE math is unchanged.
- Both physical boards pass all 1897 independent vectors with original files,
  active program, registers, stack and working directory preserved.

```sh
MK61_TEST_SANITIZERS=1 MK61_EABI_SAMPLES=10000000 tests/run_native_eabi_tests.sh
python3 tests/native_eabi_arm_self_test.py --elf BUILD/resident.elf
python3 tests/check_native_runtime_libraries.py BUILD/resident.map
python3 tools/build_portable_app.py --name ALUBENCH \
  --source tests/fixtures/eabi_cycles_probe.c --output-dir BUILD/alu
python3 tests/hil_eabi_cycles.py --port PORT --public-id ID \
  --expected-build CRC --app BUILD/alu/ALUBENCH.APP --output-dir BUILD/times
```

Both boards also passed 12 ADC probes, five restored emulator batches and 100
64-KiB NOR reads with no SPI/DMA errors. The 60-sample 64-KiB read medians are
25046 us Classic and 24768 us mini, equal to the prior startup phase. Emulator
medians are 1709889 / 1708405 cycles per step, essentially unchanged. The
public 48-case timing/preservation runner passed physically on mini as well.

The full current matched-RAM SEGGER comparison is included in the measurement
JSON; see `STM32-compact-math.md` for its precision-qualified table.

Real host-suspend/RTC/keyboard STOP qualification remains deferred to the final
USB stage. That pending hardware scenario is not counted as passed here.

The standalone SRAM benchmark exposed a supported-instruction gap in the APP
builder: internal `R_ARM_THM_JUMP19` conditional branches were rejected. Both
Python and .NET extractors now accept this position-invariant relocation only
when its symbol remains inside the APP, matching existing Thumb call/jump
rules. Regression tests reject undefined, foreign and absolute targets. This
changes build-time admission, not the firmware loader or APP format.
