# Bounded 128-bit pow kernels for RP2040

V106 is an unpromoted software candidate over V101. The
[patch](kernel-pow.patch) preserves the complete numerical and placement
delta against that frozen parent; the [report](evidence.json) pins the source,
ELF, programs, inputs and results. Production sources are not changed by this
checkpoint. The platform parent is still the provisional 53ABCF2C tree, with
the final formatter and memory-selection reconciliation pending.

## Instruction results

| Difficult pow stream | Cases | V101 instructions/call | V106 instructions/call | Qfplib composition instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 2,073.17 | 1,855.45 | 1,501.55 |
| Near one, large exponents | 5 | 1,496.00 | 1,496.00 | 1,573.80 |
| Moderate bases/exponents | 128 | 2,353.45 | 2,068.20 | 1,535.45 |

The two remaining slow streams use 10.5% and 12.1% fewer instructions than
V101. They still exceed Qfplib. The reference is `exp(mul(y,ln(x)))`, since
the pinned Qfplib has no standalone pow. Its results differ from directed
MPFR on 63, 5 and 71 cases in these streams; owned results have zero mismatches.

The same matrix contains 117 groups, 119 chunks and 23,352 inputs: 113 groups
are faster than Qfplib by instruction count, two tie and two remain slower.
No group mean increases relative to V101. The standalone square kernel uses
194.65 instead of 291.99 instructions on 171 counted endpoint-test samples.
These are executed ARM instructions with captured ROM and modeled SIO
division. Hardware cycles and speed parity remain unmeasured for this image.

## Arithmetic and source changes

Two retained 128-bit kernels are expressed in project-owned Thumb assembly.
The adjacent [C++ reference](kernels.cpp), regenerated ARM object, GNU
assembly object and final ELF have identical executable kernel bytes.
Clang is used only to reproduce that reference; the firmware still builds
with the existing GCC assembler and has no new compiler dependency.

For two 64-bit words, the partial high product omits less than three units
of the exact product divided by 2^64. Combining the two cross products and
the low product omits less than seven retained 128-bit units. Certified
error allowances become 8 when both low words are nonzero and 4 when only
one is nonzero. Zero-low exact products and the first exact square remain
exact. The largest composed radius is 57,728, below the unchanged 65,536
limit. Ambiguous enclosures retain the existing rejection and full
refinement rules; this does not introduce an approximation tolerance for
returned binary64 values.

The [certificate](certify.py) checks these bounds and source isolation. It
also verifies that replacing the generic denominator power loop with direct
squares preserves every operation for its eight admitted denominators
1, 2, 4, 8, 16, 32, 64 and 128. A numerator of one avoids an unused base copy.
Two unchanged pow entries retain their V101 addresses through dedicated
linker sections, preventing the near-one cache conflict seen in the discarded
V104 placement. No tables or global RAM allocations are added.

## Qualification and resources

Final V106 passes:

- 265,409 ARM/MPFR calls across twelve functions and all 23,352 matrix inputs.
- All 75,229 potentially affected cases selected from the existing
  1,003,177-case corpus. The earlier full-million run belongs to V86;
  this checkpoint records a fresh complete selected-subset run.
- 6,000 exact-rational interval products, 11,309 integer-power helper cases,
  10,379 square endpoint/center checks and 2,125 zero-low squares identical
  to the parent full product. Every ARM call checks ABI and bounded writes.
- Dyadic decisions over 3,412 input pairs, including 10,020 exact midpoint
  comparisons; 8,677 trusted-cell calls, 2,952 full public calls and hooks at
  149 real hot entries. There are no wrong accepted rounding decisions.
- Cortex-M4 O3 soft/hard ABI preprocessing and allocated-code identity,
  generic-M0 allocated-code identity, linked-memory runtime and source/link
  isolation checks. Three other numerical objects are unchanged. All 224
  inspected non-pow linked functions retain equivalent code and named calls
  at their prior addresses; 48 have changed call encodings.

Allocated Flash decreases by 208 bytes relative to V101; sealed image extent
remains 1,537,008 bytes. Static main RAM remains 198,856 bytes, heap 30,520
bytes and scratch usage 4,072 of 4,096 bytes. The map contains no libgcc
archive members. The selected pow corpus observes at most 2,244 stack bytes.

The cache check records 38 exact-result traces over 19 streams with the same
16 KiB, two-way, 8-byte-line model. Four variants use LRU/FIFO replacement
and whole-line/per-word fills. Near-one modeled misses per call stay at
3.6 for whole-line fills and improve from 6.8 to 6.0 for per-word fills.
Regular pow increases from 2.14–4.36 to 6.60–12.65 misses per call;
moderate pow increases from 2.73–4.97 to 6.02–11.44. Normalized ln increases
by 0.004–0.012 misses per call; the other 15 control streams are identical.
These modeled tradeoffs require physical measurements and are not hardware
cache-counter evidence.

## Reproduction

Run from the repository root with the frozen V101 and V106 work directories
recorded in the report. `kernel-pow.patch` applies to the V101 source tree.
The report records a fresh staged application reproducing all six changed
or added source files byte for byte.

```sh
/usr/bin/clang++ --target=arm-none-eabi -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -Os -std=c++17 -ffreestanding -fno-exceptions -fno-rtti -fno-unwind-tables -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -c research/m0-pow-kernel-asm-20261022/kernels.cpp -o .build/m0-pow-dyadic-loop-v106-20261022/kernels-public-reference.o
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-kernel-asm-20261022/certify.py --work .build/m0-pow-dyadic-loop-v106-20261022 --baseline-work .build/m0-pow-first-cell-v101-20261022 --reference-object .build/m0-pow-dyadic-loop-v106-20261022/kernels-public-reference.o --json .build/m0-pow-dyadic-loop-v106-20261022/public-certificate.json
```

The [square test](square-arm.py) accepts explicit `--elf`, `--baseline-elf`,
`--bootrom` and `--json` paths. Existing integer, dyadic, full-rounding,
selected-corpus and matrix runners remain in `tests/`; their exact hashes
and reports are embedded in the evidence.

General pow termination beyond the finite checked corpus remains unproved;
the final undecided 1024-bit trap is still present. The two instruction gaps,
final platform reconciliation, device timings and production promotion are
unfinished. This checkpoint uses no USB and makes no firmware installation.
