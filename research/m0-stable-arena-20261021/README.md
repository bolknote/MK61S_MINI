# Stable RP2040 math placement (V77)

This qualified offline prototype places the existing numerical code and
constants in dedicated flash sections. It preserves all 274 ordinary math
input sections' sizes and cache indices from V75, despite the platform
changing from A7483AE6 to the provisional 7AEA549E snapshot. Numerical
instructions and constant payloads in all five math object files are
byte-identical before linking.

`placement-and-arena.patch` contains the six accumulated math-file changes
and the arena insertion for the current PicoCalc CMake configuration:

```sh
git apply --check research/m0-stable-arena-20261021/placement-and-arena.patch
```

Its CMake hunk preserves the current worktree's other CMake changes. The
separate `qualification-cmake.patch` records the exact full math overlay
used on the immutable 7AEA549E platform source. Source hashes and the
qualified ELF are recorded in the measurement report.

The linker excludes these five objects from both the SDK flash catch-all
and its remaining-text RAM catch-all, then places their ordinary text and
read-only inputs in their original object order. Existing fixed hot sections
and the math RAM section retain their locations. Overlap assertions protect
the platform image, the constants and the other math sections.

Build `f6130a30` passes:

- 265,409 actual ARM / MPFR RNE checks over twelve real-valued functions.
- 44,816 exact ARM float-widening checks, including special values and ABI.
- 114 groups / 116 chunks / 23,091 comparison cases: unchanged owned
  instruction counts; 112 groups use fewer instructions than Qfplib and
  two tie. These counts are not device timings.
- M4 soft/hard-float and generic M0 code/data identity, exact-pow checks,
  negative layout tests, diagnostic CRC, reference link, APP ABI and UF2
  bounds.
- No linked libgcc archive members. Production double-operator call sites
  bind to the owned helpers, including 46 direct VM call sites.

The additional footprint over the same-platform V76 image is 16 allocated
flash bytes. The image extent remains 1,537,008 bytes. No coefficient table
is added; the existing cold data inputs total 220,134 bytes. Main static
RAM remains 198,856 bytes. Math code uses the already reserved 4 KiB region
at `0x20038000`; the platform snapshot leaves it empty, but the reservation,
heap limit and both stack boundaries are unchanged.

Four isolated cache-model variants show fewer tangent conflicts than V75,
and no new misses on the simple-power, normal-f2d or standalone-sqrt streams.
They exclude IRQ/other-core traffic and are not hardware speed evidence.

The source is still based on an **unaccepted** platform snapshot. No math
image has been flashed, and production math is unchanged. After platform
acceptance and the agreed memory-function window, use the final accepted
source and immutable restore package, then run the complete hardware matrix.
General `pow` totality outside the exact stage's 224 supported exponent
values remains unproved; its undecided trap is retained.
