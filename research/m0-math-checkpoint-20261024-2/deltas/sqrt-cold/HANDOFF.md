# sqrt(+Inf): equal Qfplib, faster cold paths

Original CPU math goal, private RP2040-only delta over frozen V164.
The single remaining historical sqrt deficit (+Inf) is now12 instructions,
equal to correct Qfplib and down from15. The entry guard now dispatches
known positive E0 directly to the unchanged subnormal path. The other cold
entry uses the carry sign already supplied by its zero check.

15,136 profiled inputs /45,408 actual ARM calls pass exact integer sqrt
RNE and directed MPFR4.2.2. Raw NaN sign/payload bits match the parent on
every call. All2048 exponent fields, both signs, coefficient boundaries,
NaN payload bits and random raw fields are represented.

| Class | Cases | Candidate versus V164 |
|---|---:|---|
|Signed zero|2|same count, same signed bits|
|+Inf|1|3 instructions faster; equal Qfplib|
|Other nonfinite|308|3 instructions faster|
|Negative finite|7398|3 instructions faster|
|Positive subnormal|253|2 instructions faster|
|Positive normal|7174|same count|

There are7960 faster and7176 equal inputs, zero slower. No selected case
loses to Qfplib where Qfplib gives the correct result. Its7959 raw wrong
answers are retained; they are not converted into speed wins. These are
executed instruction counts, not physical cycles or a fresh whole matrix.

The candidate is a bare ELF with no mapped firmware or ROM. R4-R11, SP,
bounded writes and READY/DIRTY SIO are checked on every call. Maximum
observed stack writes28 bytes (the unchanged subnormal frame plus normal
root frame). No new stack, table, global RAM or libgcc/ROM dependency.

Only the sqrt fixed and cold sections change. The fixed section remains
8544 bytes; new guard bytes consume old alignment NOPs. The coefficient
table/address remain exact. Normal code moves by8 bytes and has one
verified ADR encoding change to the same table.
The cold helper164->156 bytes: total allocated size -8. Independent public
reassembly/relink matches every executed allocated byte without exclusions;
only nonallocated object-filename metadata differs. Existing fixed slots
fit. All other allocated sections and generic M0/M4 controls match.

Sources: `native_eabi_m0.S` SHA256
`11671642973ca74fe4d1435a41d846bb96f3c426cea918e17fd489f6909fa33c`;
`native_eabi_m0_sqrt_special.S.inc` SHA256
`5a18d6553f4987a5ae173dacd02440165295ec66ebba896aa27a1644ebea4552`.
Executed ELF SHA256
`2662c539807c1cdbe9c728154ea0d83262c99e974729a9dbfb9ff847c1ee36d1`.
Integration delta: `sqrt-cold-only.patch`; reasoning: `PROOF.md`;
actual evidence: `qualification.json`, `isolation.json`.

Independent review pending. Canonical/frozen sources, Git, USB and Flash
are untouched. No firmware/version or new platform pipeline. Normal code
placement changed, so cache/cycle equality awaits actual hardware. General
pow UDF, other required speed deficits, repaired-base integration and
whole-image/hardware acceptance remain open. The full goal is not complete.
