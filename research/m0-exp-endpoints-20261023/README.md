# Checked exp endpoints for RP2040

This checkpoint preserves **V145/8498B317**, including the cumulative
four-file source delta from the committed [V138 checkpoint](../m0-pow-horner-20261023/README.md).
The exact V144 lineage is included because V145 retains its tiny/huge
exponent rules and checked small-exponent pow path. Canonical/release
sources and the coordinated V138 hardware packet are unchanged.

V145 rounds the existing Q62 exp enclosure directly on the subnormal
grid. Strict interval checks also handle zero and overflow. A midpoint
overlap retains the previous correctly rounded refinement. Coefficients,
polynomial, table and error radius5/10 remain unchanged. The new helper
uses32-bit variable shifts, with no new arithmetic table or global RAM.

On128 independently selected inputs in[-746,-700], mean executed ARM
instructions improve from **3,373.02 to593.57**, versus **640.52 for
Qfplib**. All owned results match directed MPFR; Qfplib is wrong on105
of these inputs. Both raw means and the subset where both results are
correct remain in the reports. Instruction counts use captured ROM and
modeled SIO division; they are not physical cycle measurements.

The complete expanded finite comparison retains **171 groups /30,304
cases:156 faster,2 equal,13 slower**. The original117-group matrix remains
115 faster/two equal/zero slower. Only its three exp chunks improve; the
other116 chunk records and all48 non-exp independent group records remain
exact V144 copies. No slow group was removed.

V145 has105,478 fresh directed-MPFR checked calls, including99,138 exp
calls, with zero owned errors. These include58,302 endpoint/midpoint
cases and40,196 random/special exp inputs. A separate176,440 actual ARM
helper calls check exact integer RNE at both interval endpoints. Thirty
frozen public pow canaries and the complete23,352-case original matrix
also pass. All12 selected processes reached observed terminal exit0.
The V144 evidence is historical and separately bound to its own ELF.

V145 adds392 allocated Flash bytes versus V144, or2,260 versus V138.
There is no new table, global RAM or libgcc member. Static RAM198,856,
heap30,520 and scratch4,072 bytes remain unchanged; image extent is
1,537,400 bytes. The fresh observed exp stack maximum is488 bytes.
M4 soft/hard ABI preprocessing and allocated code/data are identical to
the original baseline; generic M0 code/data also match. Other numerical
objects retain their instruction/data payloads;248 linked numerical
bodies are exact and70 have only verified equivalent veneer BL changes.
Scratch veneer positions changed, so cache/cycle equality is not claimed.

## Remaining work

- Nine huge-argument sin/cos/tan streams take roughly15,000–21,000
  instructions versus Qfplib1,350–1,617. Qfplib gives an incorrect answer
  on all128 inputs in each stream; these raw speed deficits remain recorded.
- Subnormal ln/log10/sqrt average6,064/8,056/255 instructions versus
  Qfplib8/144/12. Every Qfplib result in these three128-case streams is
  incorrect. Correct handling still has substantial optimization potential.
- Medium-integer pow averages2,191 versus1,544 instructions. Qfplib is
  wrong on113/128 cases. The full-fractional pow group also loses on its
  16-case correct-reference subset:1,732 versus1,555, despite winning
  its raw mean. Individual slow cases remain in other groups.
- Physical cycle/cache measurements and coordinated platform/cold/full
  restoration acceptance are pending. The running hardware transaction
  remains V138; this commit does not replace its candidate.
- General pow still traps if its1,024-bit interval remains undecided.
  Finite successful tests do not prove termination or correct rounding
  for every binary64 pair. A total correctly rounded path remains open.

The overall performance/accuracy goal remains active.

## Integrity and reproduction

`candidate/` and `lineage/V144/` contain byte-identical originals. Their
private paths and historical `commit_created:false` fields describe the
earlier freeze, before the human explicitly requested this checkpoint.
They have not been rewritten. Firmware/test ELF binaries are omitted;
hashes, manifests, four source snapshots and the complete source-file
hashes preserve the exact tested code. No device backups or authorization
records are included. `provenance.json` maps every archived original.

From the repository root:

```sh
python3 research/m0-exp-endpoints-20261023/verify-checkpoint.py
python3 research/m0-exp-endpoints-20261023/verify-checkpoint.py --check-local
python3 research/m0-exp-endpoints-20261023/reproduce.py --output .build/m0-exp-endpoints-reproduced
```

The first command verifies the archive without historical private files.
`--check-local` also reads the original evidence and all three source
trees. Reproduction requires exact V138 sources; use its committed
reproducer or pass an alternative with `--parent-source PATH`. Select
`--candidate V144` to reproduce that lineage instead. Add `--build --sdk
PATH --toolchain PATH` to compile in the new private directory. No command
opens USB or installs firmware. Original producer scripts write reports
and retain historical private dependencies: run copies in a fresh private
directory, preserving this archive and its frozen reports.
