# M0+ mathematical runtime: second intermediate checkpoint

This extends the source/evidence checkpoint in commit `31fc77615` with
three reviewed private optimizations and the current unfinished `atan`
residual repair. These are separate diagnostic components. They have not
been merged into the canonical runtime or a combined firmware image.

| Function / path | Saved result | Implementation |
|---|---|---|
| Signed `int64 -> double` entry | All 16 historical deficits resolved: 12 faster and 4 equal to correct Qfplib. 30,222 profiled cases, zero errors or instruction regressions versus the parent. Independent narrow technical GO. | Own assembly, Flash |
| `sqrt`, cold dispatch | `sqrt(+Inf)` is 12 instructions, equal to Qfplib; other cold paths improve by 2-3 instructions. 15,136 profiled cases, zero errors/regressions; positive normals and signed zeros retain their counts. Independent narrow technical GO. | Own assembly, Flash |
| `atan`, packing and error enclosure | 58,276 public cases, zero own errors; 24,498 profiled cases faster and 446 equal to the parent. The two historical deficits are resolved. Four expanded inputs still fall back to CORE-MATH. Independent narrow technical GO with those four speed inputs open. | Own code and CORE-MATH fallback, Flash |
| `atan`, residual repair prototype | Four selected DIRTY cases drop from 22,288-22,486 to 1,775-1,800 instructions. Two are faster than Qfplib; two still lose by 9/16 instructions. Only a 27-row public probe and a 30,408-call helper check exist. Full public qualification, current object isolation and independent review remain outstanding. **WIP; not qualified for integration.** | Own code and unchanged fallback, Flash |

The first three deltas retain their generic M0 / M4 compile-isolation
evidence. No new table or global RAM is introduced. All timings above are
executed ARM instruction counts, not physical cycles. `atan` public tests
use pinned resident runtime helpers and captured ROM support; they do not
use ROM mathematical functions. The arithmetic components and the new
residual helper can be replayed as bare diagnostic ELFs.

The prototype reuses the original quotient's numerator and denominator,
computes a bounded signed residual, and uses a six-bit Thumb divider without
SIO access. Its exact rational error enclosure is below 6 Q70 units. The
fresh helper check covers quotient magnitudes 0 through 33, preserves both
SIO states, and checks ABI, carries and bounded writes. This does not
replace a full public-function qualification.

The historical V164 list is unchanged: separate candidates now resolve
292 of its 507 deficits (287 faster, 5 equal). The remaining historical
inputs are `pow` 153, `exp` 16, `ln` 10, `sin` 22 and `cos` 14.
Expanded test sets overlap and are not added to that list. General `pow`
totality, remaining speed deficits, integration onto the repaired Pico
base, whole-image regression and physical acceptance remain open.

## Contents and verification

- `deltas/`: exact sources, integration patches, original producers and
  frozen evidence for the three reviewed components.
- `reviews/`: independent receipts and their supporting reports, including
  the now accepted subnormal-addition delta from the previous checkpoint.
- `wip/atan-residual/`: current prototype source, build/probe pins, exact
  bound and fresh helper evidence. The earlier C++ geometry trial is
  retained separately under `trials/`.
- `status/`: updated progress ledger. It does not promote a combined image.
- `provenance.json`: original private paths, raw hashes and gzip mappings.

The preceding committed checkpoint supplies the pinned V164 source and
emulator/oracle support; its complete archive is verified first. Large
reports use deterministic gzip with lossless recovery of original bytes.
Original producers retain their historical private paths and must not be
run inside this archive. Historical `not_claimed`/`pending` fields precede
the later independent receipts saved here. Binary objects, firmware,
device backups and device-access records are omitted.

```sh
python3 research/m0-math-checkpoint-20261024-2/verify.py
python3 research/m0-math-checkpoint-20261024-2/verify.py --check-local
python3 research/m0-math-checkpoint-20261024-2/verify.py \
  --build-output .build/m0-math-checkpoint-r2-replay \
  --toolchain /path/to/arm-none-eabi/bin --replay
```

The verifier rebuilds all four diagnostic ELFs and checks their original
full-file hashes. Replay executes the saved conversion/sqrt corpus against
fresh integer and MPFR references, reproduces instruction counts, and
checks the residual helper against exact unbounded rational quotients.
Public `atan`, Qfplib, parent firmware and the full library are not replayed
by this entry point. All generated output goes to a new private directory.
No command opens USB or writes firmware.
