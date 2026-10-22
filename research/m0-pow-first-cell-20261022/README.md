# One certified midpoint for first-tier pow on RP2040

V101 is a private, unpromoted candidate over the numerically identical V99
rebase of V98. The [report](evidence.json) pins the source, ELF, inputs, programs
and results. The [three-file patch](first-cell-pow.patch) applies to the
numerical V98 files as well as V99. It adds no tables or global allocations.

## Instruction results

| Difficult stream | Cases | V98/V99 instructions/call | V101 instructions/call | Original Qfplib instructions/call |
|---|---:|---:|---:|---:|
| Regular exponents | 128 | 2,407.95 | 2,073.17 | 1,501.55 |
| Near one, large exponents | 5 | 1,496.80 | 1,496.00 | 1,573.80 |
| Moderate bases/exponents | 128 | 3,041.99 | 2,353.45 | 1,535.45 |

The two remaining slow streams use 13.9% and 22.6% fewer instructions than
V98. Both still exceed Qfplib. This reference is `exp(mul(y,ln(x)))`, since the
pinned Qfplib has no standalone pow. It differs from directed MPFR on 63,
5 and 71 cases in these three streams; owned results have zero mismatches.

The unchanged matrix has 117 groups, 119 chunks and 23,352 inputs: 113 groups
use fewer instructions than Qfplib, two tie and two remain slower. No group
mean increases relative to V99. Non-pow groups and exact-exponent pow are
unchanged; several ordinary pow groups improve slightly. These are executed
ARM instructions with captured RP2040 ROM and modeled SIO division, not
physical cycle counts or a universal speed bound.

## Rounding argument

The unchanged first-tier exp enclosure has a normalized integer center
`2^62 <= q < 2^63` and radius `E <= 510`. For an ambiguous normal rounding
cell, its low ten bits `T` satisfy `|T-512| <= E`. Relative to the lower
binary64 cell, the exact result is therefore inside
`[T-E,T+E]`, strictly within `(-512,1536)` Q62 units.

Away from a binade start, this interval can round only to the lower cell or
its successor. One existing certified integer midpoint comparison chooses
between them. An overlapping midpoint enclosure still declines to the
identical full refinement. At a binade start, where the lower spacing is
smaller, the old two-boundary mode remains in use. Endpoint/domain guards,
exact sqrt-cube handling and all integer error radii are unchanged.

The original arbitrary-hint API remains separate and always selects its old
two-boundary mode. Random or poisoned hints cannot enable the trusted mode.
The new entry still receives pointers to live parameters and does not retain
or modify them. Outside the ambiguous interval, ties are impossible; sharing
the lower-cell packing and comparing the 32-bit tail gives exactly the same
RNE result while reducing hot code.

The runnable [certificate](certify.py) binds these differences to the parent
source, proves the normalized table/correction bounds, checks all 261,121
ambiguous radius/tail pairs and both retained parities for every unambiguous
tail. It relies on the unchanged, previously qualified Q62 enclosure and
integer-boundary inequalities.

## Qualification and footprint

Final V101 passes:

- 8,677 direct trusted-entry calls over 2,952 pairs, including distant
  binade-start cells and 11 aliased-parameter calls, with preserved bytes and
  canaries. All 2,952 full public calls match MPFR. Hooks at 149 actual hot
  entries independently check the two-cell property.
- The preserved arbitrary-hint suite: 3,412 pairs, 10,298 accepted hints,
  10,024 declines, 10,020 exact-power midpoint comparisons and 111 public
  MPFR calls. Its result digest is identical to V98.
- All 265,409 ARM/MPFR calls across twelve functions, all 23,352 matrix
  inputs and all 75,229 potentially affected entries selected from the
  existing 1,003,177-case corpus. The older full-million run belongs to V86;
  this is a new complete selected-subset run, not a relabeled million run.
- Cortex-M4 soft/hard O3 and generic non-RP2040 M0 isolation checks.

Only three pow includes differ from V99; 640 other source files are identical.
Four other numerical objects and their allocated relocation targets are
identical. Apart from the three intentionally changed entries, all prior
native object functions retain their instruction bytes. Of 224 inspected
non-pow linked functions, 221 keep their addresses and bytes; three unchanged
RAM shift functions move. No libgcc archive members are linked.

Main static RAM remains 198,856 bytes, heap 30,520 and image extent 1,537,008.
The scratch reservation stays 4,096 bytes, with actual use reduced from
4,088 to 4,072. Allocated Flash grows by 88 bytes over V99. Maximum observed
stack in the selected pow corpus remains 2,244 bytes.

Thirty-eight exact instruction/data traces cover 19 streams per image under
four explicit warmed cache models. Sixteen controls match. The regular hard
stream improves in three models and adds 0.031 misses/call in one; moderate
adds 0.039-0.305 misses/call. The five-case near-one stream adds 1.6 misses/call
in the two per-word-fill models and is unchanged in the whole-line models.
These tradeoffs are recorded; models do not establish physical cache policy,
prefetch, IRQ effects or device speed.

## Platform and reproduction

[V99 rebase evidence](rebase-evidence.json) records the earlier private
composition on provisional memory/platform build 53ABCF2C. Its source was
checked against `e82ac7286d288ef52ebbc885b26159cfbc525420dd51bef870b01d6ca945c64c`.
Numerical object allocations/relocations are identical to V98; all 117 matrix
groups have identical instructions and the 265,409-call rounding suite passes.
Runtime/memory, M4 and generic M0 checks also pass. Its accepted hardware
status is still pending. The coordinator has also identified a later final
diagnostic formatter (`a0301206549208deabdae1c4d7a156cc05e7bcb8f3a5ee13947de8015de3c154`)
for the eventual platform source. That source reconciliation is still pending;
the frozen V99/V101 images are preserved without silently substituting it.

```
python research/m0-pow-first-cell-20261022/certify.py --source-root .build/m0-pow-first-cell-v101-20261022/source --baseline-root .build/m0-platform-rebase-v99-20261022/source --json /tmp/pow-first-cell-certificate.json
python research/m0-pow-first-cell-20261022/first-cell-arm.py --elf .build/m0-pow-first-cell-v101-20261022/firmware/mk61s-picocalc-pico-h.elf --bootrom research/rp2040-memset-2026-10-21/capture/bootrom.bin --json /tmp/pow-first-cell-arm.json
```

V98, V99 and V101 remain separate frozen candidates. No USB access,
production promotion or additional Git commit was made for this work. The
shared release inputs/status stay at the human-requested checkpoint.

Two hard pow instruction gaps remain. General pow totality outside the exact
stage's 224 exponents remains unproved; the final undecided interval trap is
retained. Physical timing and production integration require the final accepted
platform/memory composition, a matching immutable restore and explicit device
handoff. The return-value contract is RNE; errno and FP flags are not added.
