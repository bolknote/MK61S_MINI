# M0+ mathematical runtime: intermediate R45–R47 checkpoint

This checkpoint continues `74eb87c0f`. It preserves the author-qualified
private R45 source, its complete qualification records, the unselected R46
boundary study, and the intermediate R47 normalized-exponent divider.
It changes research artifacts only. The production runtime and M4 code are
not integrated by this commit. These executables are library test images,
not PicoCalc firmware.

R45 remains the selected author-qualified private image. Its completed
campaign accounts for 2,296,597 public ARM calls. The original qualification
union contained 2,047 losing `pow` pairs, 148 division pairs and 512 `exp`
inputs. The subsequent R46 study expanded the tested domain and found a
total of **36,936 pre-existing division deficits in R45** across the joined
sets. These were newly measured cases, not regressions. Historical metadata
and counts remain unchanged in their original reports; `status/` records
the later admission and authoritative scope.

R47 is **not selected or fully qualified**. Its completed diagnostics show:

| Campaign | Inputs | R45 losing inputs | R47 losing inputs |
|---|---:|---:|---:|
| Direct division | 2,862 pairs | 148 | 0 |
| Expanded boundary division | 77,282 pairs | 36,914 | 0 |
| Targeted `pow` | 16,740 pairs | 2,047 | 2,045 |

The sets overlap; these counts must not be added as unique coverage.
R47 executed 508,704 public diagnostic ARM calls. Direct division and pow
used 19,554 fresh directed-MPFR evaluations plus 48 sNaN policy shortcuts.
The expanded campaign executed R47 afresh and explicitly reused the gold,
R45 and Qfplib results from the frozen R46 campaign. Its cached calls are
not fresh R47 calls. All three pow reference compositions are retained;
Qfplib does not provide a native pow entry here. Every correct reference
result is compared, with no nominal-domain filter. Incorrect reference
outputs and costs are retained.

R47 has zero wrong outputs and zero newly losing correct-Qfplib cases on
these finite sets. Parent increases are also preserved, including cases
that were already slower: 2,568 direct-division state rows, 48,426 expanded
state rows and 36 pow state rows. Instruction counts are not physical
cycle measurements or a universal performance bound.

The normalized exponent comes from an exact signed packed-argument
subtraction. The sign/exponent metadata is prepared before mantissa
division, and three old upper-binade adjustment instructions disappear.
Exact early paths cover certain overflow, deep underflow, the half-minimum
subnormal tie, and a subnormal numerator divided by a normal denominator.
The existing exact midpoint arithmetic and reciprocal polynomial remain.
Only two RP objects differ from R45; the other 17 objects, including the
default M0 and M4 implementations, have identical allocated code, symbols
and semantic relocations. R47 adds 160 Flash bytes, no lookup tables,
global RAM or libgcc. The 4,080-byte bank has six symbolically explained
changed bytes; literal bank identity is not claimed.

Actual linked guards pass: 16 new divider rejection controls, six retained
denominator controls, 12 native-Q8 controls, the R12/17 rejection controls,
the real-ROM loader and nine disabled-object checks. The source changes
reverse exactly to R45. Local label names such as `dd_0` are duplicated in
the linked image; the new guard identifies the actual timed branch target
instead of taking a name-dictionary entry. The rejected host-only first
attempts are retained.

Still open: the full unified R47 primary/pow/exp/ln replay, formal
composition of the inherited whole-mantissa enclosure with the new
metadata, universal correct rounding and general pow totality, float FMA
acceptance, universal stack bounds, independent acceptance, physical
timing, firmware integration and release. Historical component receipts
are retained within their original scope and do not grant R47 acceptance.

## Verification

The archive retains raw records, scripts, source snapshots, failed
preflights and frozen manifests. Repeated payloads are stored once; large
text files and whitespace-sensitive payloads use deterministic lossless gzip. `provenance.json` maps every
preserved original path to its stored bytes and records both hashes.
Objects, ELF and ROM images are omitted; executable fingerprints and
rebuild commands are included. Older reference baselines and the narrow
R35 receipt are preserved as historical evidence.

From the repository root:

```sh
python3 research/m0-math-checkpoint-20261026/verify.py
```

Optional local-original verification:

```sh
python3 research/m0-math-checkpoint-20261026/verify.py --check-local
```

Optional source rebuild into a **new** directory:

```sh
python3 research/m0-math-checkpoint-20261026/verify.py \
  --build-output .build/m0-math-checkpoint-20261026-replay \
  --toolchain /path/to/arm-none-eabi/bin
```

Verification checks archive hashes, raw diagnostic accounting and the
guard/source bindings. Rebuilding compares allocated sections, symbols
and semantic relocations for both R45 and R47, keeping the original debug
flags because they affect linker veneer order. No ARM/MPFR campaign or
device access occurs. Historical producer scripts are evidence: do not
run them inside this archive or the frozen original directories.
