# V144 small-exponent pow intervals

Private qualified candidate **4CA2268A**, source
`a0bb69978f4a071c5cf60b90d7732d9b85f57edf8e51818920a9bde1c46fed26`.
The immutable hardware transaction still names **V138/83CF4AC4**.
This candidate has not been installed, promoted, committed or pushed.

The existing cold fallback now checks two exact magnitude rules: positive
finite bases with |y|<=2^-64 round to1; finite |y|>=2^63 gives0 or infinity
for positive finite bases other than1. Between the tiny rule and |y|<2^-12,
a new interval route reuses the unchanged unrounded logarithm. A complete
integer product and an explicit floor error retain its enclosure even
after large shifts. A strict RNE-cell certificate handles sufficiently
small arguments linearly; larger ones reuse the existing checked Q62 exp
polynomial. Ambiguous cells retain the original cr_pow refinement.

`certificate.json` records exact rational bounds and the reused contracts.
Its checker verifies the logarithm code and exp prefix against V138 and
runs the existing rational coefficient/product/table checker. The helper
is also executed directly as ARM code against exact Python integers:
15,072 products, all64 shifts64..127, no discrepancy. The first failed
property attempt was a32-bit result-mask error in the harness, separately
preserved; it did not require a runtime change.

Seven newly audited pow streams improve over frozen V142:

| Domain | V142 instructions | V144 instructions | Qfplib composition |
|---|---:|---:|---:|
| y=±2^-64 | 15,780.68 | 232.00 | 1,434.77 |
| y=±2^-63 | 15,816.53 | 1,010.02 | 1,430.77 |
| y=±2^-62 | 15,924.93 | 1,009.05 | 1,432.03 |
| y=±2^-60 | 16,113.75 | 1,009.57 | 1,439.52 |
| y=±2^-50 | 16,207.21 | 1,009.37 | 1,433.28 |
| Huge finite y | 10,765.32 | 163.66 | 1,564.08 |
| x near1, variable y | 5,707.26 | 935.51 | 1,372.57 |

Each stream has128 independently directed-MPFR checked vectors. Qfplib
is correct on every vector of the first six streams; it is wrong on13
near-one vectors. Both raw means and correct-reference subsets remain in
the audit. The reference pow is exp(mul(y,ln(x))); Qfplib has no standalone
pow entry in this pinned comparison. The older168-vector normal-base
tiny-y group now averages201.77 instructions versus Qfplib1,345.80.

The full expanded report preserves **all171 groups /30,304 cases**:
**155 faster,2 equal,14 slower** by raw mean instruction count. This is
not a speed pass. The original117 groups and119 chunk records, including
result/instruction digests, remain exactly V142's115/2/0. All46 independent
groups outside the seven improvements also retain their per-vector counts.
`future-timing-corpus.json` saves all6,952 new audit/tiny vectors separately
from the approved hardware packet.

Fresh directed-MPFR calls:75,229 affected pow cases,40,395 random/special
pow pairs,39,022 small-y/cutoff/midpoint/class cases,196 tiny audit calls
and6,784 independent-domain calls: **161,626 calls, zero owned errors**.
Of these156,250 are pow. The original23,352 matrix cases and30 frozen
public-pow canaries also pass. Every ARM call checks callee-saved registers,
SP and bounded writes. `terminal-observations.json` distinguishes observed
process exits from output-file existence and preserves both failed attempts.

The candidate adds **1,868 allocated Flash bytes**:1,736 for the small-y
route/private product thunk and132 for the magnitude helper. No table,
global RAM or libgcc archive member is added. Main static RAM198,856,
heap30,520, scratch4,072 and image extent1,537,008 bytes are unchanged.
Worst observed pow stack is2,404 bytes versus V138's2,252; this is a finite
test maximum, not a proof of a universal stack bound.

All original numerical object instruction/data payloads are retained.
One old cold call changes target. At the final link250 old numerical
bodies remain byte-identical;66 differ solely at actual old THM_CALL
relocations to verified equivalent five-instruction veneers. Existing
function addresses/sizes and instruction counts are unchanged. The linker
permuted veneer slots, so scratch bytes and XIP/cache traffic are not claimed
identical. Physical cycles must be measured. M4 soft/hard ABI preprocessing
and every allocated code/data section match the original baseline exactly;
generic non-RP2040 M0 code/data also match.

`HANDOFF.json` binds the image,646-file source, reports, commands, producers
and unchanged approved-packet hashes. Run `verify.py` from the repository
root for a read-only check. Producers write in this directory: copy the
package and select new output paths before repeating a frozen experiment.
Unicorn JIT required local execution outside the macOS sandbox; all tests
were offline and opened no USB device.

Remaining work includes the14 raw deficits: nine huge-argument trig
streams, three subnormal ln/log10/sqrt streams, negative-extreme exp and
medium-integer pow. Qfplib returns incorrect values throughout the first
twelve streams. They remain recorded deficits rather than discarded data.
The full-fractional pow stream also loses on its16-vector subset where
both libraries are correct, despite winning its raw mean. Individual
outliers occur in other streams too. Physical cycles and coordinated
platform/cold/restoration acceptance remain separate. General pow still
retains its final undecided1,024-bit trap; all-input totality is unproved.
The overall goal remains active.
