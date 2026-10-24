# M0+ mathematical runtime: third intermediate checkpoint

This extends `9859eeae7` with the completed residual and geometry stages
and the latest directional/ninth-order `atan` candidate. These are private
diagnostic components, saved for review and continuation. The canonical
runtime and production firmware are unchanged.

| Stage | Saved result | Review |
|---|---|---|
| Bounded residual repair | Four earlier hard inputs now beat correct Qfplib. Full profiling of observed refinement routes exposed eleven other preexisting raw speed deficits. | Independent narrow technical GO, with tradeoffs and eleven inputs open |
| All-geometry repair | 79,096 fully profiled state cases, zero own errors; six more raw deficits resolved and seventeen observed raw deficits remain. | Independent narrow technical GO, with seventeen inputs open |
| Directional residual and short ninth term | 106,312 fully profiled state cases, zero own errors. All previous seventeen deficits now beat correct Qfplib. The expanded corpus has twenty parent deficits and two candidate deficits: eighteen resolved, none newly introduced. | Author qualification; independent review pending, two speed inputs open |

The latest component has 53,156 unique inputs, 425,248 public ARM calls
and 75,298 bare helper calls: 500,546 calls in total. The two remaining raw
inputs are `3FEF1BCDCF0D1830` and `BFEF1BCDCF0D1830`; their DIRTY paths cost
22,764/22,763 instructions versus correct Qfplib's 1,787. Every input is
profiled in both SIO states, including all incorrect Qfplib answers.

Compared with the geometry parent, 101,748 state cases improve, 4,504 are
equal and 60 regress by 17-267 instructions. Against V164, 101,800 improve,
4,504 are equal and eight regress. The latest change adds 400 code bytes,
no tables/global RAM/libgcc, and raises observed peak stack from 888 to
912 bytes. These tradeoffs and all remaining losses are saved explicitly.
Counts describe executed ARM instructions, not physical cycles.

Generic M0 and M4 allocated compile controls remain identical. Public
`atan` uses pinned resident helpers and captured ROM support; it adds no
ROM mathematics. The new primitive checks run without firmware or ROM.
The full public diagnostic ELF independently recompiles/relinks exactly;
that producer check does not substitute for independent review.

The original 507-case matrix is unchanged. Separate candidates resolve
292 historical deficits (287 faster, five equal). The remaining 215 are
`pow`153, `exp`16, `ln`10, `sin`22 and `cos`14. Expanded test sets overlap
and are not added to that count. Other operations, general `pow` totality,
combined-image integration and physical acceptance remain open.

## Contents and verification

- `deltas/`: exact sources, patches, producers and full compressed evidence
  for all three stages. The latest stage is not promoted to production.
- `reviews/`: independent residual/geometry receipts and supporting checks.
- `study/`: the separate polynomial analysis that led to the short repair;
  its older 117-121-instruction isolated kernel is not the latest runtime.
- `status/`: the current progress ledger; earlier entries remain historical.
- `provenance.json`: original paths, byte hashes and lossless gzip mappings.

The first two committed checkpoints supply the pinned source and emulator
support. Large JSON reports use deterministic gzip. Binary objects,
firmware images and device backups are omitted. Historical producers keep
their private paths and must not be run inside this archive.

```sh
python3 research/m0-math-checkpoint-20261024-3/verify.py
python3 research/m0-math-checkpoint-20261024-3/verify.py --check-local
python3 research/m0-math-checkpoint-20261024-3/verify.py \
  --build-output .build/m0-math-checkpoint-r3-replay \
  --toolchain /path/to/arm-none-eabi/bin --replay
```

The portable verifier checks both preceding archives, every saved byte,
all qualification rows and explicit deficit/regression counts. It rebuilds
the three public diagnostic components and the exact inline-source unit
to their original full ELF hashes. Optional replay repeats 75,298 bare
helper calls and fresh MPFR checks for all 53,156 saved unique inputs.
This entry point does not execute public `atan`, Qfplib or a combined image.
All generated files go to a new private directory; no USB/device is opened.
