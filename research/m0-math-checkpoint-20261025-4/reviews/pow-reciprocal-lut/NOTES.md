# PRIVATE LUT reciprocal seed: independent review

Exact supplier FROZEN7384323f, actual parent soft13dc7f81 / independent211cf956.
The parent's later ROOT receipt de2f1599 is additive evidence. The child's
frozen result correctly retains parent_ROOT_receipt=null from its seal time;
it has not been reissued. Parent acceptance does not qualify this child.

All 67 local and 1978 external pins and the separate seed-study seal were
checked. Nine own full object/ELF rebuilds are byte exact. All source except
the seed is byte-identical to the soft parent; only its194-byte suffix becomes
56 bytes of code plus256 bytes of NEW integer constants. The312-byte blob is
identical to the selected bare unit. Its address, software caller, root BL,
guards and the282-byte common RNE tail are unchanged. Allocation grows1050 to
1168 bytes, with no new RAM or libgcc dependency. DefaultM0/M4 code stays equal.

The table contains128 little-endian uint16 values
floor(2^32/(65536+512*i+256)). Actual ADR/LDRH decoding binds its address.
For65536<=D<=131071, i=(D>>9)-128 is0..127 and the byte index is0..254,
always halfword-aligned. The independent integer proof covers the entire
65536-element domain. It derives the signed folded product, signed multiply
and arithmetic shifts, not just a floating-point estimate. In particular,
signed32(2p mod2^32)=2(p-2^31) because |p-2^31|<2^30. The u*e product fits
signed32. The low32 multiply/MVN residual equals the true signed N-qD even
where qD crosses2^32. Its initial quotient error is[-1,3]; correction preserves
qD+r=N, needs at most three downward or one upward step, and ends with the
unique floor(N/D). Intentional modular products are not described as lacking
overflow. Five pure binding controls reject altered/truncated/unaligned
tables; altered tables were not executed or qualified.

The full saved bare stream covers all65536 D plus12304 flag/boundary tests.
All77840 rows and every repeated-D timing were recounted. The selected
instruction range is20-27; other measured maxima are34,42,86. Its unique
best complete-domain worst instruction count selects lut128_floor. The
discarded sample-only choice lut32_ceil_outer and all variants' common
prediction of nine public fixes are historical forecasts, not selection
or public qualification. Selected old+new155680 calls are separate from
233520 exploratory calls to other variants. Physical cycles are unmeasured.

R3 is a NEW permitted leaf clobber. Its old preservation contract was not
inherited. Own bounded leaf tests execute527 old/new pairs (1054 Thumb calls),
with all16 NZCV values at32 bin-edge inputs plus exact-domain adversaries.
They verify exact quotient and remainder, one aligned in-table LDRH, no
writes or stack accesses, R1/R12/PCS/SP/PC, and actual costs matching the
saved domain. R3 changes to the residual and is not assumed preserved.

Fresh linked caller disassembly shows push{R0-R3,R7}, seed BL, consumption
of the returned quotient in R6, and pop{R0-R3,R7} before the common join.
Twenty-five actual DIRTY traces (14 direct,11 public) explicitly witness
saved R3, different leaf R3, and restoration of the saved operand at the
join. They also verify raw operands, guarded R6, original20-byte frame,
R12, SP, seed-call8alignment, common flags and preservation of all7 SIO
words without divider writes. Thus this clobber is qualified for the actual
private caller, not an arbitrary continuation or scalar C prototype.

Own qualification totals1578 CPU-only Thumb calls in Unicorn:1054 leaf,
248 direct on31 pairs and276 public on23 pairs. There are50 directed MPFR
inputs and4 separate sNaN policy shortcuts. The parent direct test explicitly
uses the private hint alias, avoiding the author's preserved wrong-symbol
preflight. All9 new strict fixes were executed in both SIO states against
all numerically correct real Qfplib references. Wrong reference results and
costs remain in the records. READY costs stay equal. No failed or discarded
own calls occurred.

One own public-report keyword retained the old name all48_fixes... through
an AST driver adaptation. Actual assertion9, statusALL9 and raw23pairs were
already correct. PUBLIC-REPORT-CORRIGENDUM.json binds that exact executed
source/report and corrects the label to all9_fixes... without changing
records or repeating ARM/MPFR. This qualification claims nine, not48.

Saved full qualification was independently recounted against the immediate
soft parent:120980 pairs,241960 states,279522 reference variants, including
77106 wrong Qfplib variants. Loss pairs11386 to11377:9 strict fixes,377 DIRTY
states saving59-73 instructions, zero wrong/new losses/increases. Every
public and direct delta equals the measured selected-seed delta. Current
parent cost is the overwritten parent_reciprocal_instructions field; older
values in historical streams are not substituted. All10254 fresh public
control rows match, and all4148 direct rows retain their timing/outputs,
including936 wrong Qfplib variants. Original153 stays119 strict/34 slower.

Author476133 qualified calls,6761 MPFR,184 sNaN and256 direct dyadic inputs
are separate evidence. Failed author24ARM/3MPFR calibration, unselected
233520 calls, parent qualification/pilot and old66288 seed are excluded.
No fresh original153 pilot was run; its score comes from the full raw.

The current1168-byte section occupies free Flash below2MiB. The full saved
stack peak remains2284, author controls2148 each, and changed-parent388 is
a subset rather than a full comparator. Own selected public peaks968 and
direct176 are equal in all three images. No universal stack/cycle claim is
made. Reviewed507 remains422; author437 is a separate union. Near-one is
still a sibling. Future source merge/relink, actual integrated shared R12,
loader/layout checks and the old168-byte overlay's14-byte table hazard
remain mandatory. This receipt gives no general pow totality, global ddiv,
main, hardware or release GO. No device/network/Git/canonical edits occurred.
