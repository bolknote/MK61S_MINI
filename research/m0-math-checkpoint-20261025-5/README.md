# M0+ mathematical runtime: ninth intermediate checkpoint

This checkpoint continues commit a5ebd486bf251602be4467bf9dde14a4793a53e9.
It saves the first unified source tree and source-linked math executable,
the exact reciprocal remainder certificate and its subsequent optimizations,
and the completed independent component reviews. The canonical runtime,
default M0 and M4 implementations and release firmware are unchanged.

The unified tree combines the qualified pow table product, square and
boundary helpers, near-one exp and latest private reciprocal implementation.
All calls use real linked symbols. Its candidate and previous-loop timing
control link without libgcc or Qfplib objects and without unresolved symbols.
The exact reciprocal seed table remains 256 bytes. The library's existing
CORE-MATH fallback data is retained; this checkpoint adds no large table.

The actual linked R12 producer, wrapper and consumer pass the static guard
and 17 rejection controls. The source loader runs on both linked images in
the ARM emulator with real Boot ROM bytes. It restores all 4,080 hot-code
bytes and the SDK memory pointers after RAM poisoning; the reserved 16-byte
bank tail remains untouched. A host-only negative control detects the
14-byte corruption that an obsolete product overlay would cause. No old
firmware overlay is loaded or executed by the unified harness.

These are library link, private-contract and loader checks. The two explicit
loader calls are separate from two automatic ROM lookup initializations in
the harness. No unified mathematical operation or MPFR numerical campaign
has run yet. Historical phase metadata is preserved unchanged and can say
"not linked" or "guard pending"; the completed later proof files and
CHECKPOINT-STATUS.json describe the current stage. This ELF is not a
bootable PicoCalc firmware.

The separately qualified private positive-one-numerator reciprocal now has
zero Qfplib instruction deficits on both saved scalar campaigns: 41,988
states including IEEE edges and flags, and 262,144 normal-mantissa states
covering all 65,536 seed divisors with two patterns. Incorrect Qfplib outputs
and their costs remain in the records. The latest correction removes three
instructions on the affected path, adds eight code bytes, and retains the
old exact loop as a timing control because its branch direction changes.
Instruction counts do not establish physical cycle parity or a universal
performance bound, and this private entry is not generic division.

The same 120,980-pair public pow corpus retains 11,369 losing pairs and the
original 153-input pow matrix retains 33. The exact certificate introduced
32 parent-cost increases; the later changes do not erase this ancestral
tradeoff. The saved corrigendum corrects the earlier certificate report.
Separate-component historical coverage is 438/507 author-qualified and
422/507 independently reviewed; those are not results from the unified ELF.
Inline, certificate, zero and bound3 component reviews are saved. ROOT
receipts present at preservation time are recorded individually; none is
whole-library performance or release acceptance.

## Verification

Sources, build recipes, proof reports, failed preflights and raw numeric
records are preserved with hashes. Binary objects, ELF and ROM images are
omitted. Large text and JSON files use deterministic lossless gzip. The
rebuild recipes retain allocated code, symbols and semantic relocations;
required local SDK headers and licenses are included. Do not run historical
producer scripts in this archive or frozen original directories.

The unified rebuild retains the original debug-generation flags. Removing
them changes this linker's generated veneer ordering even when input code
fingerprints match. Debug path bytes are not compared; the resulting
allocated sections, symbols and semantic relocations are compared exactly.

From the repository root:

    python3 research/m0-math-checkpoint-20261025-5/verify.py --check-local

Optional rebuild into a new directory:

    python3 research/m0-math-checkpoint-20261025-5/verify.py \
      --build-output .build/m0-math-checkpoint-r9-replay \
      --toolchain /path/to/arm-none-eabi/bin

Verification checks the archive chain, raw public/scalar accounting, proof
bindings and optional source rebuilds. It runs no ARM/MPFR campaign and
accesses no device. Overall work remains open: unified numerical and
instruction qualification, remaining operation deficits, general pow
totality, physical measurements, firmware integration and release checks.
