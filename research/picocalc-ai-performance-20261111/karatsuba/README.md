# Private Karatsuba tests for the PicoCalc AI runtime

The test suite executes the actual ARMv6-M instructions against the retained
**7C38C634 / 8A17554E** firmware and the captured RP2040 ROM3. It does not
replace production arithmetic or access the device. `host-results.json`
records the numerical checks, instruction counts and exponential call traces.

Two private binary64 candidates use one level of Karatsuba on the 53-bit
significands: a difference form and a sum form that falls back on carry.
Both retain the shipped RP2040 normal guards, short-mantissa paths and
rounding/packing. An SRAM copy of the actual shipped routine is the control;
its instruction counts match the resident routine on every timed operand.
The generic non-RP2040 helper is not the performance reference.

## Physical comparison at 270 MHz

The one on-device APP run completed on **7C38C634 / 8A17554E**. All 256
MPFR-derived scalar cases per variant and 128 full-product checks passed
before timing. Median calls, after subtraction of the same ABI-loop control:

| Implementation | Microseconds per call | Cycles per call | Against SRAM control |
| --- | ---: | ---: | ---: |
| Current resident | 0.559814 | 151.150 | +1.3% time |
| Identical SRAM control | 0.552734 | 149.238 | +0.0% time |
| Karatsuba, differences | 0.770752 | 208.103 | +39.4% time |
| Karatsuba, guarded sums | 0.723145 | 195.249 | +30.8% time |

Both Karatsuba prototypes are slower: the best costs about 31% more time
than the same-location control. The ordinary resident path is also faster
than either candidate. No candidate was installed in the production runtime,
and a full inference rerun would not establish a speed gain for these kernels.
The scalar results and all eight timing samples are in `hardware-results.json`;
`hardware-receipt.json` records the single run, unchanged firmware/settings,
clock restoration to 125 MHz, removal of the owned APP directory, and closed
CDC/root lease. The first preflight attempt made no device writes because USB
was disconnected; the actual benchmark was run once after reconnection.

## Completed offline checks

- 5,336 MPFR cases per implementation: current resident, SRAM control and
  both candidates. Normal numbers, signs, low-word carries, exact rounding
  midpoints and neighbours, subnormals, zeros, infinities and NaNs passed.
  Finite outputs match bit for bit; NaNs are compared by classification.
- 4,937 complete 106-bit integer products per implementation match Python
  integer multiplication, including all low and sticky bits. These checks
  cover carry cases which rounded FP64 results can conceal.
- Callee-saved registers, stack restoration and the allowed write ranges
  are checked by the existing ARM emulator harness.
- Actual `mk61_m0_exp` output remains unchanged when its FP64 multiply entry
  is redirected to either candidate, including 37 calls on the four tested
  extreme inputs which enter its refinement/fallback.

| Implementation | Mean executed instructions | Mean `MULS` |
| --- | ---: | ---: |
| Best resident | 124.796875 | 16 |
| Identical SRAM control | 124.796875 | 16 |
| Karatsuba, differences | 164.468750 | 12 |
| Karatsuba, guarded sums | 157.632813 | 12.031250 |

These are dynamic instruction counts over 128 normal operands, **not cycle
counts or physical timings**. The guarded-sum mean includes one carry
fallback. Fewer multiply instructions did not reduce total instructions in
these prototypes.

## Relevance to AI exponential

The trace covers 128 finite FP32 inputs from [-30,8], 23 boundary/special
binary64 inputs, and the actual AI FP32 exponential wrapper on the 128
finite inputs. The wrapper makes 128 exact FP32-to-FP64 conversions and 128
FP64-to-FP32 conversions, but **zero calls to `__aeabi_dmul`**. Its ordinary
exponential runs in fixed point. Four of the 23 boundary inputs do reach the
fallback, making 37 FP64 multiply calls in total. The probe records individual
inputs and paths; this is not a claim about every possible model activation.

Changing only FP64 multiply therefore has no effect on the tested ordinary
exponential path. There is no candidate full-inference timing or speedup
claim. The retained 0.4277315/0.442951 s/token measurements remain the reference.

## Build and run

From the repository root, using a Python environment with MPFR and Unicorn:

```sh
python3 tests/build_m0_karatsuba_benchmark.py \
  --resident-elf .build/mk61ai/math-choice-20261111/firmware-candidate/mk61s-picocalc-pico-h.elf \
  --output-dir .build/mk61ai/karatsuba-20261111
python3 tests/m0_karatsuba_arm_self_test.py \
  --package-dir .build/mk61ai/karatsuba-20261111
```

The builder also produces a **6,148-byte KARAMUL.APP**, using 10,696 bytes of
loaded SRAM. It was run once on the board for the comparison above. It checks the exact resident footer before calling any
pinned firmware addresses. It tests correctness before timing, rotates four
variants over eight rounds of 2,048 calls with equal call-loop controls, uses
the hardware microsecond timer at 270 MHz, and restores the starting 125 MHz
clock before writing `KARAOUT.BIN` to its own APP directory. No firmware,
settings, model or global math patch is performed. Use a fresh owned APP
directory and the normal device coordinator handoff for a physical run.

The report decoder requires no Unicorn or device access:

```sh
python3 tests/m0_karatsuba_arm_self_test.py \
  --decode-result /path/to/KARAOUT.BIN --output /path/to/timings.json
```

`package.json` pins the exact resident ELF, both runtime source files,
test sources, generated vectors, private assembly, relocatable ELF and APP.
The ELF and generated corpus stay in the local build directory.
