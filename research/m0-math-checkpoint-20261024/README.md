# M0+ mathematical runtime: intermediate checkpoint

This preserves the mathematical work since the committed V145 checkpoint:
the frozen **V164/0B3BE556** math components and five subsequent arithmetic
deltas. Canonical runtime and platform sources are unchanged. This is an
offline research checkpoint; it does not install or promote firmware.

| Function / path | Saved result | Implementation |
|---|---|---|
| `double + / -`, ordinary mixed signs | All 17 historical slow cases improved; 10,807 targeted cases without errors. Narrow independent GO. | Own assembly, Flash |
| `double + / -`, largest normal exponents | 11,018 targeted cases without errors; 2,071 selected normal pairs no slower than correct Qfplib. Narrow independent GO. | Own assembly, Flash |
| `double + / -`, low normal and Inf/NaN | 44,455 targeted cases without errors; 762 earlier deficits resolved. Narrow independent GO. | Own assembly, Flash |
| `double + / -`, zero and subnormal inputs | 70,261 cases / 210,783 ARM calls without errors. All 18 remaining earlier deficits improved: mean 20.89 instructions versus 64.78 for correct Qfplib. Independent review pending at this checkpoint. | Own assembly, Flash; no C++ fallback or ROM |
| `double -> uint32` | 47,966 cases without errors. All 256 historical slow cases: 20-22 instructions versus 43 for Qfplib. Narrow independent GO. | Own assembly, Flash |
| Other required arithmetic and mathematical functions | V164 source, numerical evidence, instruction matrix and remaining individual deficits preserved. No new whole-library qualification claimed. | Own code and CORE-MATH in Flash; no ROM math in this candidate |
| General `pow` | Still incomplete: the last 1,024-bit refinement can reach UDF if undecided. Successful tests do not prove totality. | Own code and CORE-MATH, Flash |

The latest add/sub candidate has 3,015 profiled cases: 2,623 faster than its
parent, 392 equal, zero slower. None loses to Qfplib where Qfplib is correct
on this profiled set. Another 1,768 controls retain exactly the parent's
results and instruction counts. Its public 1,472-byte block matches the
executed diagnostic body without exclusions; it adds 268 bytes over the
low-normal parent, no tables or global RAM. The standalone object has no
undefined symbols or relocations. Observed stack writes use 20 bytes.

All figures above count executed ARM instructions, not physical cycles.
Unprofiled cases support correctness only. Expanded test sets overlap and
must not be added to the historical V164 list of 507 slow inputs. The
historical list and raw incorrect Qfplib outputs remain intact. The initial
mixed-sign and uint32 deltas improve 273 entries of that historical list
in separate diagnostic objects; no merged whole-image result is implied.

The baseline M4 soft/hard and generic M0 isolation evidence is retained.
Later deltas retain their object-level isolation checks. These compile
controls do not amount to a fresh whole M4 firmware rebuild. No libgcc
dependency is added. Tables already present in V164 are archived as source;
the subsequent arithmetic deltas add no approximation tables.

## Contents and verification

- `baseline-v164/source/`: all 64 pinned math components, including the
  historical linker fragment. Preserve accepted platform/memory fixes when
  integrating; this is not a replacement platform tree.
- `baseline-v164/evidence/`: frozen evidence and original producer scripts.
- `deltas/`: exact sources, patches, original producers and test reports.
- `reviews/`: four independent narrow review receipts and their evidence.
- `support/`: frozen emulator, ELF reader and integer/MPFR test oracles.
- `provenance.json`: original paths and hashes for every copied artifact.

Large JSON reports use deterministic gzip; decompression recovers the exact
original bytes. No ELF/object/firmware binaries, device backups, USB lease
or approval records are committed. Historical fields such as
`canonical_or_frozen_changed:false` describe the original qualification,
before the explicit human request to commit this checkpoint. Original
producer scripts keep their historical private dependencies and should not
be run in this archive. The checkpoint verifier is the supported entry:

```sh
python3 research/m0-math-checkpoint-20261024/verify.py
python3 research/m0-math-checkpoint-20261024/verify.py --check-local
python3 research/m0-math-checkpoint-20261024/verify.py \
  --build-output .build/m0-math-checkpoint-replay \
  --toolchain /path/to/arm-none-eabi/bin --replay
```

The first command checks the archive without historical `.build` files.
`--check-local` additionally compares the original private artifacts.
Building uses the saved diagnostic assembly and linker scripts and checks
the original ELF hashes. Replay requires Python with Unicorn and host MPFR;
it executes the latest add/sub and uint32 candidates against fresh integer
and MPFR references and compares saved profiled instruction counts. It
does not rerun the V164 firmware or Qfplib. All output goes to a new private
directory; no command opens USB or writes firmware.

Remaining work: remaining required-function speed deficits, total general
`pow`, integration of accepted math deltas onto the repaired Pico base,
whole-image regression checks, physical timings and hardware acceptance.
The complete performance/accuracy goal remains open.
