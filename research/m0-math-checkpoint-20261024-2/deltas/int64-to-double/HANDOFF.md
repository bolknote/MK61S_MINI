# int64 -> double: remove the remaining historical deficits

Original CPU math goal, private RP2040-only delta over immutable V164.
The signed entry now detects a complemented high word of zero and avoids
redundant64-bit magnitude/zero handling. RNE packing kernels are unchanged.

All16 historical slow inputs are now no slower than correct Qfplib:

| Cases | Candidate | V164 | Qfplib |
|---:|---:|---:|---:|
|4|41|46|41|
|4|23|28|26|
|5|28|33|31|
|3|43|48|46|

30,222 profiled inputs /90,666 actual ARM calls pass independent unbounded
integer RNE and MPFR4.2.2. These cover signed/unsigned64-bit and32-bit
conversion entries, all bit lengths, raw random words, sign/complement
boundaries, low-word borrow, all possible discarded-bit widths, halfway
parity and mantissa carry. Candidate, parent and Qfplib all give the correct
result on this set. The candidate eliminates420 observed signed64 losses
against Qfplib, with zero remaining/new losses on the selected set.
There are6899 faster cases and23,323 equal cases versus the parent, none
slower. The historical16 are part of this set; expanded counts must not be
added to the old507-input library matrix.

The candidate is executed as a bare ELF without mapped firmware or ROM.
It writes zero stack bytes, preserves R4-R11 and SP, and preserves READY/
DIRTY SIO on every call. All instruction counts are measured execution,
not physical Pico cycles. The old parent uses its pinned resident ELF and
captured ROM; Qfplib uses the existing separate reference ELF.

Public conversion section876->884 bytes (+8). Full884 public bytes and
all four entry offsets match the executed ELF without exclusions. No
standalone undefined symbols/relocations, no new dependencies, tables or
global RAM. All other allocated sections match the parent. Generic M0
matches all14,468 allocated bytes. M4 soft/hard compile controls match
(this source is off-target there, not a new whole-M4 firmware rebuild).

Source `native_eabi_m0_convert.inc` SHA256
`cdb5955b2acc0fe6a0f2f157da60d8af0e1cc895bbda0faa7ce9b657e55f3dc2`.
Diagnostic ELF SHA256
`a905d4bc8a1e1ac48e9164bbf8bdbb8086dec72eeea409291651d3adff0d8f90`.
Full object SHA256
`7aafbf8734c90100f495962249202a2563c322b9b70bdc02572d7eb1b7d136f6`.

`signed64-entry-only.patch` is the integration delta; `PROOF.md` explains
the complete signed entry partition and1/5-instruction savings. Numerical
evidence is in `qualification.json`; isolation is in `isolation.json`.
The earlier uint32 delta touches another part of this include and is not
merged or claimed qualified as a composite image here.

Independent review is pending. No canonical/frozen source, Git, USB or
Flash was modified for this delta. No firmware version or new platform
pipeline was created. The original full library goal remains open:
remaining required functions, general pow UDF/totality, repaired-base
integration, full-image verification and physical hardware acceptance.
