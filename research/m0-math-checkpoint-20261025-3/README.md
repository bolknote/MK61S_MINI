# M0+ mathematical runtime: seventh intermediate checkpoint

This checkpoint continues `7bfad29cf926c7db8dea88bb5d1a33b64fbcced3`.
It saves completed qualification of the exact square kernel, the new
rounding-boundary implementation, and the unfinished software-division seed.
The sources remain private diagnostic components awaiting integration.

| Saved work | Result and scope |
|---|---|
| Exact 128-bit square | Full qualification: 330,880 fresh ARM calls. On the same expanded 120,980-pair corpus, loss pairs fall from 11,449 to 11,434, with fifteen strict fixes and no new losses or incorrect results. Independent review and private-component acceptance are saved. |
| Exact rounding boundary | Reuses the square kernel without changing the complete 24-byte operands or decisions. On that same corpus, 454 public state cases save 4–180 instructions. Loss pairs remain 11,434; there are no new losses, incorrect results or parent cost increases. Qualification comprises 309,938 fresh ARM calls. Independent review is pending at this checkpoint. |
| Software seed for division | Exact `floor((2^32-1)/D)` for all 65,536 divisors from 65,536 through 131,071. There were 66,288 bare ARM calls including additional flag-boundary controls. The function occupies 194 bytes, executes 82–97 instructions, preserves R12 and uses no stack or memory writes. It is **not yet connected to binary64 division**. |
| Reciprocal profile | Five distinct real root-path denominators were profiled. Existing division takes 29–600 instructions depending on the input and SIO state. This is diagnostic evidence, not a speed claim for the unfinished software divider. |
| Rejected 80-bit boundary filter | Every one of 56 pilot boundary calls fell back, adding 262–904 instructions. The experiment and exact-gap analysis are preserved, excluded from qualification and integration. |

All comparisons retain numerically incorrect Qfplib outputs and costs.
The expanded corpus has 279,522 reference-state variants, including 77,106
incorrect Qfplib variants. Every numerically correct reference is compared;
there is no nominal-domain filter. Each new component has 5,051 fresh
directed MPFR checks plus 76 sNaN policy shortcuts, reported separately.
Pilot calls and inherited reference/oracle results are not counted as fresh.

The square kernel saves 27–41 instructions per call and reduces the measured
kernel-plus-helper stack from 68 to 60 bytes. Its 232-byte body retains the
old 310-byte slot. The boundary body adds 228 diagnostic bytes and reduces
the measured bare boundary stack from 212 to 156 bytes. The whole public
corpus still has an observed 2,284-byte stack peak; this is not a universal
stack bound. Counts describe executed Thumb instructions, not device cycles.
Default M0 and M4 selected source controls remain equal.

The original 153-point `pow` matrix improves from 35 to 34 remaining losses
after the square replacement. The later boundary change does not change
that count. The author's separate historical 507-input union is 437 resolved
(431 faster, six equal), with 70 remaining: `pow` 34, `sin` 22, `cos` 14.
The separately reviewed union remains 422. These are separate component
results, not one integrated executable or a universal speed guarantee.

## Evidence and historical corrections

`components/` preserves the immutable square r2 and boundary author packets.
The square r2 seal supersedes a rejected seal that accidentally pinned an
empty log before stdout appended to it. Its rejection and reissue records
are saved; the numerical evidence was copied without new calls.
`reviews/` and `receipts/` preserve the later square review and acceptance.
Live, unfinished boundary-review files are not snapshotted.

The frozen boundary result and handoff incorrectly report an upper saving
of 169 instructions, carried over from the original pilot. The separate
`corrections/boundary-public-range.json` binds those immutable files and
records the correct full-corpus range, 4–180. The verifier recounts the raw
records and checks both 180-instruction witnesses. Frozen files are unchanged.

`work-in-progress/ddiv-seed17/` contains source, build recipe and completed
bare proof. Its explicit checkpoint status supersedes the earlier build-only
status; it does not qualify a public divider. `analysis/` retains profiling
and rejected-filter evidence. `status/` is a historical ledger and contains
older fields; the explicit checkpoint status states the saved scope.

Binary objects, firmware, ROM images and ELF files are omitted. Their hashes,
allocated-code fingerprints and source rebuild recipes are retained. Large
JSON files use deterministic lossless gzip. `provenance.json` records the
original bytes and paths. Historical producers must not be run in the
archive or frozen directories.

## Verification and remaining work

```sh
python3 research/m0-math-checkpoint-20261025-3/verify.py --check-local
python3 research/m0-math-checkpoint-20261025-3/verify.py \
  --build-output .build/m0-math-checkpoint-r7-replay \
  --toolchain /path/to/arm-none-eabi/bin
```

Verification checks the previous archive chain, hashes, lossless encoding,
review bindings and saved raw accounting. Optional rebuilding materializes
only archived sources into a fresh directory and compares allocated bytes,
symbols and semantic relocations for 32 outputs: thirteen square outputs,
seventeen boundary outputs and two seed outputs. Embedded input paths in
linker scripts are remapped as well as command arguments. Debug-path bytes
are excluded. Verification executes no ARM or MPFR campaign and accesses
no device.

Remaining work includes software-divider integration and qualification,
boundary review, remaining speed paths, general `pow` totality, source merge
and relink with the separate near-one `exp` sibling, actual integrated R12
consumer and loader/layout checks, physical measurements and release
acceptance. The old 168-byte product overlay overlaps fourteen bytes of the
new table entry and cannot be reused. The overall goal remains open.
