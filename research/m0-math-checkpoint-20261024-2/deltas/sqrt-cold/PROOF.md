# sqrt cold guard partition and flags

The existing guard extracts R3=R1>>20 and rejects all negative inputs and
positive exponent2047 before checking positive exponent0. Positive normal
inputs execute exactly the same six guard instructions and reach the
unchanged normal arithmetic. The new layout has two cold zero checks:
one for known positive E0 and one for negative/nonfinite inputs. Each is
the same `LSLS R2,R1,#1; ORRS R2,R0; BNE target; BX LR` sequence as before.
The shifted high word OR low word is zero exactly for signed zero. Both
zero signs return with the same instruction count and original bits.

A nonzero positive E0 input enters `mk61_m0_sqrt_subnormal`, an alias of
the parent's subnormal stack/scaling/root code. No repeated E0 classifier
is needed, saving two instructions. The source from its push through its
return/literal pool is unchanged, including the uint64 converter and
exact scaling. R3 remains zero at that entry.

For the other nonzero cold entry, LSLS puts original R1 bit31 into carry.
Thumb ORRS and BNE preserve carry. Thus C is exactly the input sign on
entry to `mk61_m0_sqrt_special`. BCS selects the same old negative branch
without its previous E0 and sign comparisons. A positive input admitted
there must have exponent2047. Fraction-zero returns +Inf; nonzero fraction
uses the unchanged NaN quieting. The negative branch also retains the
old exponent test, negative finite canonical NaN, and negative Inf/NaN
sign/payload policy. These nonzero negative/nonfinite paths save three
instructions, including +Inf:15->12, equal to correct Qfplib.

The main fixed section stays8544 bytes. Eight new guard bytes consume
eight existing alignment NOP bytes. Normal instructions and literals move
by8, with one checked ADR R4 encoding change: old offset0x56/new0x5e both
address the coefficient table at offset0x160. Every other corresponding
normal instruction/literal byte matches. The full coefficient table and
its address remain exact. The cold section164->156 bytes, so the two
allocated sections shrink by8 in total. Existing fixed slots still fit;
no linker fragment is changed.

Fresh public objects match the objects used for execution. Independent
relinking reproduces all allocated code/data and symbol addresses exactly,
without excluded instruction bytes. Only nonallocated .symtab/.strtab
file-name metadata differs (`main.o` versus `candidate-main.o`, value0).
All other allocated sections match the parent. Generic M0 and M4 compile
controls match. The standalone ELF has no undefined symbols/relocations,
ROM mapping, firmware mapping or libgcc dependency. It contains only the
normal sqrt/table, cold helper and unchanged integer conversion section.

Correctness of the numerical sqrt kernel is inherited. This partition
argument and the exact integer/MPFR checks cover the changed dispatch;
the finite instruction comparison does not prove all-input cycle speed.
Instruction placement changed, so physical cache/cycle equality for normal
roots is not claimed. No production integration or hardware acceptance.
