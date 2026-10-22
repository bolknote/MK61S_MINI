# Smaller bounded pow products on the final PicoCalc platform

V110 is an unpromoted software candidate. Its two-file
[math patch](small-cross-pow.patch) applies to V106. It is also rebased onto
the exact frozen 2EABB2A2 platform, including the final formatter. The
[report](evidence.json) pins the source, ELF, inputs, programs and results.
Production sources and the shared index are unchanged.

The two-file figure is strictly incremental relative to V106. Relative to
the frozen final 2EABB2A2 platform, the complete accumulated work changes
15 files and adds five, including CMake, the linker extension and core_math.
The [scope manifest](source-scope.json) enumerates both bases and all exact
20 paths with before/after hashes. The
[complete platform patch](full-math-from-platform.patch) reproduces the whole
V110 source tree from that final platform. Future full-firmware hardware
acceptance must cover this complete delta.

## Instruction results

| Difficult pow stream | Cases | V106 instructions/call | V110 instructions/call | Qfplib composition instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 1,855.45 | 1,813.22 | 1,501.55 |
| Near one, large exponents | 5 | 1,496.00 | 1,496.00 | 1,573.80 |
| Moderate bases/exponents | 128 | 2,068.20 | 2,003.52 | 1,535.45 |

The two remaining slow streams improve by 2.3% and 3.1% relative to V106.
Both still exceed Qfplib. The reference is `exp(mul(y,ln(x)))`, since the
pinned Qfplib has no standalone pow. It differs from directed MPFR on 63,
5 and 71 inputs in these streams; owned results have zero mismatches.

The same matrix has 117 groups, 119 chunks and 23,352 inputs: 113 groups
use fewer instructions than Qfplib, two tie and two remain slower. No group
or chunk mean increases relative to V106. Two ordinary negative-base pow
streams also improve slightly. The square kernel uses 181.99 instead of
194.65 instructions on the same 171 counted endpoint-test samples.

These are executed ARM instructions with captured RP2040 ROM and modeled
SIO division. They are not physical cycles or proof of all-input speed parity.

## Arithmetic and comparison

The retained precision remains 128 bits. A three-product high32 helper
underestimates the exact real high part by less than three units. The two
such terms and the omitted low product give less than seven units for each
cross-high64 result. Combining two cross terms loses less than fifteen
retained 128-bit units. Conservative allowances become 16 when both low
words are nonzero and 8 when only one is nonzero. The largest composed
radius is 115,456, below 131,072; both fit the existing 32-bit error field.

Zero-low products and the first exact square retain their original exactness,
including sqrt-cube midpoint ties. The existing domain, strict comparison,
ambiguous-enclosure rejection and full refinement rules remain in force.
No approximation tolerance is added to returned binary64 values.

The comparator receives read-only references and avoids copying both
24-byte intervals through the argument stack. When aligned centers share
their upper 96 bits, their exact difference is the ordered low32 difference.
Other cases retain the same full subtraction and one-bit alignment rules.
The [source certificate](certify.py) binds these changes to V106 and proves
the propagated bounds. The [ARM comparator test](compare-arm.py) separately
checks exact integer endpoint ordering, carries, aliases and preserved inputs.

The [C++ reference](kernels.cpp), regenerated ARM object, GNU-assembled
kernels and final ELF have identical executable kernel bytes. The firmware
uses its existing GNU assembler; Clang is only an optional reference
reproduction tool. There are no new tables, global allocations or compiler
dependencies in these two incremental changes relative to V106.

## Qualification and resources

Final V110 passes:

- 265,409 ARM/MPFR calls across twelve functions and all 23,352 matrix inputs.
- All 75,229 potentially affected cases selected from the existing
  1,003,177-case corpus. The older full-million run belongs to V86; this is
  a fresh complete selected-subset run for the final ELF.
- 6,000 exact-rational interval products, 11,309 integer-power cases,
  10,379 square endpoint/center checks and 2,125 zero-low squares identical
  to the parent full product. Every ARM call checks ABI and bounded writes.
- 21,176 comparator calls, including 4,011 aliases and 8,497 equal-high96
  cases; every accepted sign separates independent exact original endpoints.
- Dyadic decisions over 3,412 pairs with 10,020 exact midpoint comparisons;
  8,677 trusted-cell calls, 2,952 full public calls and 149 actual hot-entry
  witnesses. There are no wrong accepted rounding decisions.
- Cortex-M4 O3 soft/hard ABI preprocessing and allocated-code identity,
  generic-M0 allocated-code identity, linked-memory runtime and source/link
  audits. All 224 inspected non-pow bodies remain identical at the same
  addresses relative to V106.

Allocated Flash decreases by 80 bytes relative to V106; image extent remains
1,537,008 bytes. Static main RAM remains 198,856 bytes, heap 30,520 bytes and
scratch use 4,072 of the same 4,096 reserved bytes. The map contains no libgcc
archive members. The selected pow corpus observes at most 2,244 stack bytes.

The cache audit records 38 exact-result traces over 19 streams with a
16 KiB, two-way, 8-byte-line model. Four variants use LRU/FIFO replacement
and whole-line/per-word fills. Only the two difficult pow streams change:
regular falls from 6.60–12.65 to 4.34–8.35 modeled misses per call; moderate
falls from 6.02–11.44 to 1.05–2.25. Each variant improves, and the other
17 streams are identical. These are explicit model assumptions and not
measured hardware cache counters.

## Final platform and rejected routing experiment

The exact platform parent has source SHA256
`32a52b706c6a47a9c25c71cf6b5a7874c3b7933808280a43af811360c41be8b7`.
Its only change from provisional 53ABCF2C is the final formatter,
`code/crash_dump_format.cpp`, SHA256
`a0301206549208deabdae1c4d7a156cc05e7bcb8f3a5ee13947de8015de3c154`.
V110 preserves all 568 non-math platform files. This selection means every
regular final-platform file outside the explicitly enumerated 76 historical
math/build overlay paths; five overlay paths are additions absent from that
platform. The final tree has 644 regular files versus 639 in the platform,
or 626 versus 621 files included in the build fingerprint. The rebase retains all five
numerical object allocations/relocations and all 303 surviving sized linked
numerical bodies at their exact addresses relative to V109.

The formatter is already available in commit
`8ee9c5c9db0a230b277ebe59db3406916c539755`. Fresh application of the two-file
math patch to V106 plus that exact formatter reproduces all three changed
source files byte for byte. Full source fingerprints and object/link checks
cover the remaining files. The V3 Flash memory selection and formatter are
reconciled; full platform hardware acceptance is still pending.

An independent offline review confirmed the full 20-path scope and exact
source/ELF/BIN/UF2 hashes. A separate narrow review confirmed the three Flash
memory bodies, runtime slots and aliases. Its focused allocator/init probe
uses the exact V110 heap bounds and passed Markdown 15,296-byte, image
8,326-byte and APP 30,000-byte allocations and release. This probe is not
execution of the complete firmware or the on-device APP loader. Both review
receipts and their historical reviewed HANDOFF are preserved in the report.

V108 also tried earlier checked integer powers. That reduced the difficult
means further, but ordinary negative-integer pow grew from 855 to 1,116
instructions. The broader first attempt even added a third Qfplib deficit.
These routing changes are excluded from V110; their measured tradeoffs are
retained in the report. Integer dispatch is identical to V106.

## Reproduction and remaining work

From the repository root, with the frozen work directories recorded in the
report, regenerate the optional reference and run the certificate:

The complete platform patch applies to a fresh copy of the frozen final
source; all 644 resulting files and the full source fingerprint were checked
against V110. Apply it with `git apply --whitespace=nowarn`: it preserves the
original trailing spaces in one upstream comment copied from `pow.c` into
`pow_accurate_body.inc`. The frozen numerical source is unchanged.

```sh
/usr/bin/clang++ --target=arm-none-eabi -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -Os -std=c++17 -ffreestanding -fno-exceptions -fno-rtti -fno-unwind-tables -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -c research/m0-pow-small-cross-20261023/kernels.cpp -o .build/m0-pow-final-parent-v110-20261023/kernels-public-reference.o
.build/picocalc-apps-arm-venv/bin/python research/m0-pow-small-cross-20261023/certify.py --work .build/m0-pow-final-parent-v110-20261023 --baseline-work .build/m0-pow-dyadic-loop-v106-20261022 --reference-object .build/m0-pow-final-parent-v110-20261023/kernels-public-reference.o --json .build/m0-pow-final-parent-v110-20261023/certificate.json
```

The comparator and [square test](square-arm.py) accept explicit ELF, ROM and
output paths. Existing integer, dyadic, full-rounding, selected-corpus and
matrix runners remain in `tests/`; their hashes and full reports are embedded
in the evidence.

Two hard pow instruction gaps remain. General pow termination beyond the
finite checked domains is unproved, and the final undecided 1024-bit trap
remains. Matching device measurements, full platform acceptance and production
promotion are unfinished. This work uses no USB or firmware installation.
