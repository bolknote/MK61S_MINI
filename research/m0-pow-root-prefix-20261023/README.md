# Bounded root prefix for RP2040 pow

V122 is the current software research candidate, build `A62D1F7C`.
This checkpoint preserves its source patch, C++ reference, GNU assembly,
qualification reports and the unfinished [V123 factor experiment](../m0-pow-factor-20261023/README.md).
The candidate has not been promoted to production or installed on the device.
Cortex-M4 and generic M0 implementations remain unchanged.

## Instruction results

| Difficult pow stream | Cases | V110 instructions/call | V122 instructions/call | Qfplib composition |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 1,813.22 | 1,497.01 | 1,501.55 |
| Near one, large exponents | 5 | 1,496.00 | 1,509.60 | 1,573.80 |
| Moderate bases/exponents | 128 | 2,003.52 | 1,918.47 | 1,535.45 |

The complete matrix has 117 groups, 119 chunks and 23,352 cases: 114 groups
use fewer instructions than Qfplib, two tie and one remains slower. The
moderate pow stream still takes about 25% more instructions than the
reference. The regular stream clears its instruction target
by only 4.54 instructions/call, so subsequent routing changes must retain
the complete matrix check.

Qfplib is evaluated as `exp(mul(y,ln(x)))`, because the pinned library has
no standalone pow. It disagrees with directed MPFR on 63, five and 71 cases
in these three streams; owned results have no mismatches. These are
executed ARM instructions with the captured ROM and modeled SIO division,
not physical cycles or an all-input speed guarantee.

## Algorithm and scope

For admitted positive normal inputs and reduced exponents `+/-p/2^d`,
`p <= 32`, `d <= 7`, a bounded 128-bit numerator feeds a short fixed-point
root chain. The high64 projection carries an explicit radius, and each
root propagates that interval. Strict midpoint comparisons certify returned
binary64 values; ambiguous or unsupported cases retain the existing
refinement. This adds no rounding tolerance.

The raw root reuses the existing 8 KiB coefficient table. Its analytical
point error is below two Q63 units; the implementation conservatively uses
radius three. The numerator radius is at most 14,032; projection reduces it
to two high64 units, and the root chain radius is at most 12. Guarded cached
reciprocal decisions preserve the existing two-cell certificate.

The [incremental patch](root-prefix-from-V110.patch) changes four files and
adds two relative to the frozen [V110 candidate](../m0-pow-small-cross-20261023/README.md).
The [scope manifest](source-scope.json) also records the complete delta from
the final `2EABB2A2` platform: 15 modified files and seven additions, with
all 568 non-math platform files preserved. Those counts include all earlier
math work; the four-plus-two figure describes only this checkpoint's
increment. The [source file hashes](source-files.json) cover every regular
file in both complete source trees.

The firmware source uses GCC and GNU as. The frozen assembly is included
by the existing RP2040 assembly unit; no Clang dependency is added to the
firmware build. Clang is used only for the optional C++ reference schedule.
The GNU proof checks exact kernel allocations and named relocations. The
whole diagnostic image is not byte-identical: two identical veneers move
and five calls follow their equivalent named targets.

## Qualification and limits

The [evidence bundle](evidence.json) retains original report hashes and
contents. V121 received fresh successful runs of 494,206 ARM/MPFR calls
across twelve functions, all 75,229 affected pow cases, 6,000 exact-base
state comparisons, 6,000 exact root interval checks and 10,286 additional
power inputs. Cortex-M4 soft/hard ABI and generic M0 isolation, linked
memory runtime and source/kernel/resource audits also passed.

V122 changes only the linker placement of the identical raw root. Its
explicit equivalence bridge checks five complete numerical object
allocation/relocation payloads and 313 surviving linked numerical functions.
V121 correctness reports retain their original ELF hashes and are reused
through that bridge; they are not described as fresh V122 executions.
V122 has fresh matrix, runtime, attribution-profile and cache reports.
The earlier full 1,003,177-case run belongs to V86.

Static main RAM remains 198,856 bytes, the heap 30,520 bytes and scratch use
4,072 of 4,096 bytes. Image extent remains 1,537,008 bytes. There are no new
arithmetic tables, global allocations or linked libgcc archive members.
The selected corpus observed up to 2,252 stack bytes. The three existing
Flash memory bodies retain identical addresses and bytes.

Cache traces cover 19 streams with four explicit 16 KiB/two-way/8-byte-line
models. Relative to V110, regular pow misses rise from 4.34–8.35 to
6.84–12.98 per call and moderate misses from 1.05–2.25 to 1.80–4.48;
near-one misses improve. V122 reduces the moderate misses relative to V121
by placing the raw root in an existing Flash gap. These model results do
not establish physical cycle parity.

The remaining work is the moderate pow instruction deficit, physical
measurements, complete platform hardware acceptance, production promotion
and general pow termination. The final undecided 1024-bit trap still
exists; finite successful tests do not establish totality or all-input
correct rounding.

## Reproduction

The checkpoint contains no firmware binaries. Their exact hashes, build
manifest and compiler provenance are preserved in the evidence. The frozen
V110 source/build and SDK/toolchain directories named there are local
reproduction dependencies. The preceding V110 checkpoint includes its
complete patch from the final platform.

From the repository root, validate the archive and reproduce all V122
source bytes into a new private directory:

```sh
python3 research/m0-pow-root-prefix-20261023/verify-checkpoint.py --check-local
python3 research/m0-pow-root-prefix-20261023/reproduce.py --output .build/m0-pow-root-prefix-checkpoint-reproduced
```

Omit `--check-local` when the historical private artifacts are unavailable;
archive integrity and the internal report bindings are still checked.
The reproducer defaults to the pinned V110 source; `--parent-source` can
select another byte-identical copy. Add `--build --sdk PATH --toolchain PATH`
to build with `tools/build_picocalc.py`. Nothing is flashed or installed.

The raw-root and composed-prefix ARM runners accept `--elf` and `--json`.
Existing matrix, full-rounding, selected-corpus and linked-memory runners
remain in `tests/`. Analytical, GNU-freeze, source-validation, equivalence
and cache producers are also archived. Their sole interface adjustment is
an explicit `--work` instead of selecting the script's own directory;
their recorded historical source/build dependencies must be present.
Use a copied private work directory when rerunning those producers, since
they write their report and, for GNU freezing, intermediate objects there.
Original producer hashes are kept separately from these interface adapters.
