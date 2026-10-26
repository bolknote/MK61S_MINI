# M0+ mathematical runtime: eighth intermediate checkpoint

This checkpoint continues commit 5001421b5fe8bb047b5d9b9ca423de1b604655ed.
It preserves the private reciprocal implementation used inside pow, its
qualification records, completed component reviews, and an unfinished
remainder-sign experiment. These sources are not integrated into the
canonical runtime or a release firmware.

| Saved component | Result on the same 120,980-pair pow corpus | Status |
|---|---|---|
| Software division seed on the DIRTY SIO path | Loss pairs 11,434 → 11,386; 48 strict fixes | Qualified and independently reviewed; private-component acceptance saved |
| Exact seed with a 256-byte table | 11,386 → 11,377; nine strict fixes | Qualified and independently reviewed; private-component acceptance saved |
| Specialization for positive numerator one | 11,377 → 11,372; five strict fixes | Qualified and independently reviewed; private-component acceptance saved |
| Inline seed and exact tiny-denominator overflow | 11,372 → 11,371; one strict fix | Qualified author packet; independent review pending |
| Exact remainder-sign certificate | Integer model passed 338,416 cases; two ARM test programs compiled | ARM execution and integration not yet performed |

The latest qualified component accelerates 754 public state cases by 2–7
instructions relative to its immediate parent. It has no public parent-cost
increases or new Qfplib losses on this corpus. Its separate, expanded scalar
reciprocal campaign has 20,994 input/flag cases and 41,988 SIO states:
7,422 parent loss states fall to 13. All 9,600 incorrect scalar Qfplib
results remain in the records. There are also 9,664 scalar parent-cost
increases of 2, 8 or 11 instructions; none creates a new Qfplib loss.
This is a positive-one-numerator private entry, not a general division API.

The exact seed is floor((2^32-1)/D) for every D from 65,536 through 131,071.
The selected bare implementation occupies 312 bytes, including its 256-byte
table, and executes 20–27 instructions. Other table variants and a rejected
sample-only selection are retained as experiments. The inline component
uses the same table values and removes allocation of the standalone seed.
Its private code grows from 1,060 to 1,072 bytes, adds no RAM or libgcc
dependency, and leaves selected default-M0/M4 controls equal.

The latest packet contains 615,606 fresh qualified ARM emulator calls,
26,011 directed MPFR inputs and 110 separately counted sNaN policy shortcuts.
Older campaigns, failed runs and superseded sources are not fresh calls in
that total. Instruction counts are executed Thumb instructions, not hardware
cycles. The observed whole-corpus stack peak remains 2,284 bytes; it is not
a universal bound. Across the four successive components the same public
corpus retains 279,522 reference variants, including 77,106 incorrect
Qfplib variants, and compares every numerically correct reference.

The original 153-input pow matrix remains at 34 losses. The author's
historical union of separate components remains 437 of 507 no slower
(431 strict, six equal); the independently reviewed union remains 422.
There is no claim of a single integrated executable or universal parity.

## Preservation and verification

The archive saves immutable author packets, completed boundary/reciprocal
reviews and acceptance receipts, the scalar reporting correction, original
source/build recipes, and a snapshot of the unfinished certificate study.
The correction records normal reciprocal lag as READY 2–5 instructions and
DIRTY 15–21, rather than the older report's unqualified 2–5 range.
The latest inline review is still live and is excluded from this checkpoint.
Historical producers must not be run in this archive or frozen directories.

Binary objects, ELF/firmware and ROM images are omitted. Hashes and allocated
code fingerprints are retained. Large JSON reports use deterministic,
lossless gzip; provenance binds each archived file to its original bytes.

Run the verifier from the repository root:

    python3 research/m0-math-checkpoint-20261025-4/verify.py --check-local

Optional source rebuild into a fresh directory:

    python3 research/m0-math-checkpoint-20261025-4/verify.py \
      --build-output .build/m0-math-checkpoint-r8-replay \
      --toolchain /path/to/arm-none-eabi/bin

The verifier checks the archive chain, hashes, review/receipt bindings and
raw public/scalar accounting. Rebuilding compares allocated bytes, symbols
and semantic relocations for 102 outputs from the saved source. Neither
verification mode runs an ARM/MPFR campaign or accesses a device.

Still open: the 13 sampled reciprocal deficits, the certificate's ARM
validation, other remaining math deficits and general pow totality, source
merge/relink with near-one exp, actual integrated R12 and loader/layout
guards, physical measurements and release acceptance. The old 168-byte
product overlay overlaps 14 bytes of the new table entry and must not be
reused. The overall goal remains open.
