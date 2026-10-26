# Qualification accounting and diagnostic layout

The first link experiment tried to preserve every Flash section's old
absolute address separately. That introduced duplicate GNU linker stubs
at section ends and failed before any public ARM execution. These failed
layout artifacts are not qualified code. The second layout keeps the
public ASM entry, all three modified CPP call-site sections and the full
scratch bank at their original addresses. Other existing pow code and
constants move into free private diagnostic Flash. Actual linked GNU
stubs and the original real Flash/RAM wrappers execute during measurement.
There are no manual branch patches or arithmetic substitutes.

The control has the accepted C77 source. Its 168-byte product write
originally left fourteen dead bytes of the resident kernel's old slot.
The diagnostic control preserves those bytes, and the old dead 24-byte
public-entry tail, so unrelated resident data and wrapper locations stay
intact. Both images have the same 4,080-byte scratch extent. The new source
adds sixteen allocated bytes in the RAM input section (including two
implicit alignment bytes) and a sixteen-byte Flash wrapper: 32 bytes total.
No new lookup table is introduced. The diagnostic Flash range contains
58,256/58,272 bytes of relocated existing code and constants, rather than
an additional algorithmic table. Integrated firmware GC/size is unmeasured.

The pilot's 3,096 ARM calls are excluded from qualified totals. Its inputs
are deliberately reexecuted within the later fresh controls. The first
full-replay launcher ran before corpus creation completed and exited at a
file read, before creating a Machine or executing ARM. It contributes zero
calls. Initial corpus assertions detected reference provenance differences;
they did not alter any mathematical input, result or reference cost.

The full inherited union comes from all three frozen R reports:
`qualification.json`, `targeted.json` and `probe.json`. The latter was a
qualified focused report in R, despite its filename. Including it is
necessary to retain all 223,976 reference/state variants, rather than just
223,826 variants from the first two reports. The targeted report uses
`qfp_composed_pow_exact` when its rows omit the reference name. The corpus
builder reproduces R's original reference selection and checks every
duplicate candidate bit and instruction count.

The fifth tracked checkpoint omitted generic `probe.json` files. In R's
case this omitted qualified focused rows from that portable archive,
although its frozen manifest, source hashes and full private original
remain intact. This packet therefore also saves R's focused report
losslessly under `lineage/`. A future tracked checkpoint must preserve
that report and this note. No numerical conclusion or old frozen file is
rewritten.

Fresh qualification totals are 314,546 actual ARM calls: 223,824 complete
old-corpus candidate calls, 58,332 fresh public control/reference calls,
and 32,390 bare-kernel calls. Old MPFR, R, C77 and Qfplib calls are inherited,
not counted again. The new 4,861 input pairs use 4,785 actual directed MPFR
validations plus 76 explicit sNaN policy shortcuts. Duplicate inputs across
fresh phases count as real executions, while union statistics deduplicate
inputs, states and reference symbols.

The wider union has 116,468 pairs. Its parent has 10,866 raw loss pairs
and this candidate has 10,853: thirteen fixed, zero new. The old 111,912
pairs separately improve from 7,901 to 7,888. These counts on different
corpora must not be subtracted to claim a regression. All new measured
losses were already present in the parent. All 8,024 parent cost increases
of two instructions and all incorrect Qfplib results remain explicit.
The observed 2,284-byte full-call stack is identical in parent/control/
candidate on the new corpus; the earlier smaller corpus peaked at 2,236.

The original 153 pow inputs now have 118 strictly faster results and 35
remaining deficits. The separate-component author507 union can therefore
increase from423 to436 (430 strict, six equal), with71 remaining
(pow35/sin22/cos14). Reviewed507 stays422 until an explicit independent
union decision. This packet is not integrated-library, hardware, physical
cycle, general-pow totality or release acceptance.
