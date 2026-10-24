# Exact reviewed delta

The child is source52e3a6f0 / ELFcc8ac311, with control ELF exactly the
accepted main-raw parent b82a9f1f. This is a private component review,
not a whole-ln/507/canonical/shipping/hardware verdict.

The new naked entry first checks the original low word for zero. Only
then can `(high<<1)==0` identify either signed zero, or exact high word
0x7ff00000 identify positive infinity. Thus ±0 return negative infinity
without altering an input payload, and +Inf returns its original bits.
Nonzero low payloads cannot take either shortcut. Negative infinity and
all signed NaNs instead reach the inherited special implementation.

Otherwise `field=high>>20` contains sign plus all exponent bits. The
condition `((field+1)>>11)==0 && field!=0` holds exactly for field1..2046,
the positive normal inputs, independently of every fraction bit. Field
addition cannot overflow. The complete4096-field partition is checked on
host; bounded actual ARM controls exercise class boundaries, zero/nonzero
high fractions, quiet/signalling/maximal NaN payloads and low words.

Forwarding uses `b` to the outlined normal implementation, or `ldr/bx`
to the existing special implementation. It leaves original R0/R1, SP and
LR intact and only clobbers caller-saved R2/R3 and flags. Every own bare
and actual public target-entry check verifies the64 original input bits,
SP8, exact SP and unchanged LR before the target executes. The direct
shortcuts do not touch SP or SIO. The bare unit's16-byte stack maximum
comes from synthetic tagged C++ targets, not from the naked entry.

# Numerical and object inheritance

The complete preceding numerical source, including raw main, near,
polynomial, tables, pack gates and fallback, matches the now-accepted
parent. The original normal source after its former classifier is exact.
The generic M0 classifier retains its original meaning. Therefore this
child does not introduce a new error radius or rounding premise.

Outlining loses the compiler's positive-input fact about raw main. Its
object replaces one `lsrs#20` by `lsls#1;lsrs#21`, explicitly dropping
the sign bit. On all routed positive normal inputs sign is already zero,
so the result is equal. The whole remaining instruction stream, literal
values and ordered relocation types/targets match, with one alignment
NOP. Independent old-to-new instruction/literal mapping additionally
checks69 internal branch and PC-load targets; it does not accept arbitrary
branch-address changes through normalization. `objdump -z` is required
to include zero-valued literal words; the first own parser attempt lacked
that option and stopped before any ARM test. That checker-only attempt
is retained. No producer file changed.

The only changed allocated sections are public entry1300→48 bytes,
outlined positive normal0→1264, and raw main1356→1360: net+16 bytes.
Other allocated code, tables, BSS and dependencies are unchanged. All39
resident bindings match the actual accepted resident, including wrapped
memory aliases. Whole private CPP+ASM objects and entire ELF, plus the
bare classifier unit, independently rebuild byte-exactly. Generic M0
allocated controls match the accepted parent. M4 controls are excluded
zero-allocated TUs; they establish no whole-M4 math/firmware claim.

# Bounded execution and honest costs

Own fresh checks comprise336 public calls (56 raw inputs, two SIO states,
candidate/accepted parent/Qfplib) using MPFR4.2.2 and416 bare classifier
calls (208 raw patterns, two states). Candidate errors are zero; original
NaN bits match parent, DIRTY28 bytes are restored, READY does not leak
dirty state, PCS/SP and bounded writes are checked. Bare SIO accesses
are zero. Actual public forwarding covers46 special and60 normal states,
including3 raw entries and2 inherited fallback calls.

Direct public costs are6 instructions for either signed zero and8 for
+Inf, compared with Qfplib8/6/10. The finite saved corpus is recounted,
not rerun: all97536 parent state counts survive, exactly those three
IEEE raw deficits close,46 raw deficits remain, and no newly slower
correct-reference input appears. Parent regressions remain19562×+1,
1026×+4,8344×+5,2022×+6 instructions. ln2 DIRTY622 versus parent617 and
Qfplib711 is not hidden. Instructions are not physical cycles. Own public
stack subset520 bytes does not replace the author's wider640-byte bound.

# Q77 dependency closure

The old conditional Q77 receipt1c2a3bdb named exactly two unaccepted
parents: main-raw split and IEEE cold entry. The first is now accepted by
54dc555c; this separate review addresses the second. Exact Q77 control
ELF/object/ratio object are byte-identical to this cold-entry candidate.
Consequently those named parent-chain premises can be discharged for
the unchanged exact Q77 tuple, while its existing local proof and all
cost/coverage limits remain as written. The old conditional receipt is
immutable; an additive closure record states this dependency result.
This does not review any ln2-sign child, establish all-input speed,
increment reviewed298/507, or grant canonical, integration or hardware GO.
