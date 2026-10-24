The source parent is the frozen adaptive-exp/81-instruction-product packet.
Its independent review is pending. This child changes no numerical admission,
refinement, endpoint, quiet-NaN, signed-zero or rounding policy.

The only changed C++ expression replaces the rounded product when table index
is zero. The unchanged Q62 table has A[0]=2^62 exactly. Write its16-bit limbs
as a0=a1=a2=0 and a3=2^14. The three terms omitted by the existing13-term
product have i+j<2, so all are identically zero. Its returned integer is

  floor((A[0]*b+2^63)/2^64) = floor((b+2)/4).

The original reduction/polynomial certificate bounds |delta|+2 strictly below
2^54. certify.py re-evaluates that rational bound and binds the actual linked
table and full-source replacement. Thus b+2 cannot overflow uint64, and the
literal constant shift returns exactly the previous integer, for every input
that reaches this branch. There is no weaker accuracy mode or new rounding
decision. Every previous RNE enclosure/refinement proof remains applicable.
The source-bound literal unit uses an independent exact128-bit integer product
oracle, and full public exp is checked separately with directed MPFR.

The shared leaf retains the same PUSH{r0-r7,lr}. If entry SP=S, it writes the
same36 bytes at S-36..S-1 in both versions. Previously SUBsp4 allocated a40-byte
frame, and MOVr3,sp/ADDr3,4 selected argument base S-36. The child omits SUB
and ADD, using MOVr3,sp directly. Every argument load therefore has the exact
same absolute address and bits. All144 bytes of arithmetic through MOVr1,r6
are byte-identical. Initial flags cannot matter: the first ADC is preceded by
an unchanged flag-setting ADD. Final POP is also byte-identical.

The only changed epilogue instruction is ADDsp16 instead of ADDsp20. In both
versions it advances SP to S-20, where the same saved r4-r7/LR are restored.
Returns, r0/r1 values, preserved registers, SP and all writes are equivalent
for every raw argument pair. There are no internal calls. The straight-line
leaf costs81->79 instructions. Frame allocation is40->36 bytes; bytes actually
written remain36. The body shrinks162->158 bytes, and ten nonexecuted NOP bytes
outside the function retain the established168-byte slot, all following symbol
addresses, relocations and section contents.

SP remains word-aligned throughout, and retains its incoming8-byte alignment
at entry/return. This satisfies the universal4-byte and public-interface8-byte
stack constraints in the Arm AAPCS32 sections6.2.1.1/6.2.1.2:
https://github.com/ARM-software/abi-aa/blob/main/aapcs32/aapcs32.rst
There is no BL/BLX while the leaf frame is active. This change requires no new
global RAM, table, ROM math, arithmetic mock or libgcc dependency. Hardware
interrupt timing and physical device cycles are not claimed by the CPU proof.

Complete RP CPP/ASM and bare-unit/public-overlay rebuilds bind the tested bytes.
All other RP allocated CPP sections and semantic relocations, and all ASM
bytes/relocations/symbol addresses outside the retained product slot, are
unchanged. Selected genericM0 and M4soft/hard objects remain byte-equivalent.
The existing472-byte tiny helper and all3736 bytes of refinement are unchanged.
This is a private component; combined integration and hardware acceptance remain
open, as do remaining speed and general totality requirements.
