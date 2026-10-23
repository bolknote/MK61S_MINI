# Bounded Horner pow for RP2040

This intermediate checkpoint preserves software candidate **V138**, build
`83CF4AC4`, including the exact five-file source delta from
[V122](../m0-pow-root-prefix-20261023/README.md), the C++ reference, frozen
GNU assembly, analytical certificates and completed qualification reports.
The firmware has not been promoted or installed. Cortex-M4 and generic M0
isolation checks passed without changing their allocated code or data.

## Instruction results

| Difficult pow stream | Cases | V122 instructions/call | V138 instructions/call | Qfplib composition |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 1,497.01 | 1,424.45 | 1,501.55 |
| Near one, large exponents | 5 | 1,509.60 | 1,507.60 | 1,573.80 |
| Moderate bases/exponents | 128 | 1,918.47 | 1,532.34 | 1,535.45 |

The fresh complete matrix contains **117 groups, 119 chunks and 23,352
cases: 115 groups are faster, two tie and none is slower** in executed ARM
instructions. The moderate stream clears its target by only 3.12
instructions/call. Physical cycle parity remains unmeasured.

The pinned Qfplib has no standalone pow; its reference is
`exp(mul(y,ln(x)))`. That composition disagrees with directed MPFR on 63,
five and 71 cases in these three streams. Owned results have zero
mismatches. Instruction counts use the captured ROM and modeled SIO
division; they do not establish physical speed or an all-input guarantee.

## Changes and qualification

Admitted positive fractional powers use a Horner ladder: take a bounded
root and multiply by the exact base at each selected numerator bit.
Proper negative fractions use the bounded inverse-root ladder. The full
128-bit numerator is constructed lazily for ambiguous rounding decisions.
Strict midpoint decisions and refinement remain in place.

The shared retained-128 product schedule, five-bit numerator decoder,
signed raw-root correction and placement in existing Flash gaps reduce
instruction work. The analytical raw-root point error is below two Q63
units; the implementation retains radius three. Positive Horner and
negative factor radii are bounded by 100 and 1,936 respectively.

All eleven qualification jobs completed successfully for the exact V138
ELF. Fresh checks include 494,206 ARM/MPFR calls across twelve operations,
all 75,229 affected pow cases, 12,397 additional direct powers, 26,144
raw-root endpoint cases, Q64 interval/alias/inverse-root checks, and 18,000
retained-128 state comparisons. The selected pow corpus observed at most
2,252 stack bytes. The older full 1,003,177-case run belongs to V86.

Four complete numerical object allocation/relocation payloads and 206
non-pow linked function bodies remain unchanged from V122. The existing
8,192-byte root and 2,048-byte reciprocal seed tables retain identical
addresses and contents. No arithmetic table, global RAM allocation,
libgcc archive member or firmware compiler dependency is added. Static
main RAM is 198,856 bytes, heap 30,520 bytes, scratch 4,072/4,096 bytes and
image extent 1,537,008 bytes. Allocated XIP grows by 2,168 bytes from V122.

The incremental scope is five modifications and zero additions. The full
delta from platform `2EABB2A2` is fifteen modifications and seven additions;
all 568 non-math source files remain identical. The
[scope report](reports/source_scope.json) records both comparisons.

## Remaining work

Nineteen traced streams were checked with four explicit cache models.
The regular and moderate streams have more modeled misses than V122;
the instruction gain therefore needs physical cycle measurements against
Qfplib. Hardware acceptance of the full platform delta and production
promotion are pending.

General pow still has a final trap when the 1,024-bit enclosure remains
undecided. These finite tests and guarded fast-path certificates do not
prove totality or correct rounding for every binary64 input. The overall
accuracy/performance goal remains open.

## Archive and reproduction

[HANDOFF.json](HANDOFF.json), the build manifest and reports are exact
copies of the pre-checkpoint evidence. Their historical `commit_created`,
`new_commits_authorized` and Git HEAD fields describe that earlier moment;
the human subsequently explicitly requested this checkpoint. Original
files in the private candidate directory were not edited.

The archive contains no firmware binaries. Their hashes and build
provenance are pinned in the handoff. The patch, five source snapshots and
complete V122/V138 file hashes preserve all changed code. The optional C++
reference uses Clang; the firmware itself builds with GCC and GNU as.
Original producer scripts and commands are preserved without rewriting
their historical private paths. Rerunning those producers requires their
recorded dependencies and a copied private work directory; do not run
them in this archive or overwrite the frozen candidate reports.

From the repository root:

```sh
python3 research/m0-pow-horner-20261023/verify-checkpoint.py --check-local
python3 research/m0-pow-horner-20261023/reproduce.py --output .build/m0-pow-horner-checkpoint-reproduced
```

Without historical private artifacts, omit `--check-local` to verify the
archive and its internal evidence bindings. The reproducer requires the
pinned V122 source tree, which can itself be reconstructed using its
committed checkpoint. Select a byte-identical alternative with
`--parent-source PATH`. Add `--build --sdk PATH --toolchain PATH` to build
in the new private directory. Neither command accesses USB or installs
firmware.
