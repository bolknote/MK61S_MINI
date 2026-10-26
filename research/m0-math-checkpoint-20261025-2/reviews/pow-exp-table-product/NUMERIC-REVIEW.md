This is a table-only scalar-equivalence component, based on the accepted
directed-product source. The separately accepted near-one delta is a sibling,
not present in this pow ELF. It requires a future source merge and relink.

All512 actual linked Q62 roots match the frozen resident table byte for byte.
Only index0 has low32=0, and it is exactly2^62; all others have nonzero low32.
The three changed caller relocations pass an unmodified literal table root.
Their allocated CPP instruction/data bytes and remaining semantic relocations
are unchanged. No generic caller is redirected. The existing exp R12 consumer
is not retained in this diagnostic pow ELF and is not newly qualified here.

For A=2^62, all omitted terms of the old truncated product are zero. Its
internal half-up result for every B64 is floor((B+2)/4), equivalently
(B>>2)+bit1(B). This is not an IEEE rounding rule by itself. Write B=h*2^32+l.
The dyadic path produces ((h&3)<<30)|(l>>2) as low and h>>2 as high; the fields
do not overlap. LSR(l,2) supplies bit1(l) in C. ORRS/MOVS preserve that carry;
the two ADCS propagate it through the64-bit return. Even B=2^64-1 returns
2^62 without overflow. This proves universal scalar identity in the stated
table domain; it does not promise identity for other A with low32=0.

For every other table root, the selector's CMP/BNE change no argument register
and tail-enter the byte-identical original77-instruction body. The scalar
return and original R12 fraction are therefore preserved, with only2 extra
instructions. All16 incoming NZCV values are independently checked. The
dyadic path uses10 instructions, writes no stack, and promises no R12 extra.

Fresh linked disassembly proves one direct RAM call, one actual GNU tail
veneer and one explicit Flash wrapper, all targeting the new entry. Both
tail veneers restore r0 and SP before BX without changing LR. Every caller
immediately captures only scalar r0/r1. The original general entry still
captures r4 in R12 immediately before rounding, and the original real16-byte
Flash wrapper still targets that general entry. No exp consumer is invented
inside the pow ELF. Future integration must rerun its actual exp R12 guard.

Actual bounded public execution confirms candidate-parent cost=2g-67d,
where g/d are actual generic/dyadic table calls. It also preserves raw results,
three Qfplib compositions, both SIO states and all13 original strict fixes.
The broader saved records, independently recounted without ARM/MPFR replay,
bind all10081 known C77-sensitive states and use C77=R-7n. Incorrect Qfplib
variants and the8024 increases of2 instructions are retained.

The R/probe.json filename denotes qualified focused evidence, unlike this
packet's excluded3096-call pilot. Independent reconstruction retains223976
old reference/state variants:223826 without that report plus150 probe-only
variants. The additional lossless gzip matches its original547596 bytes.
Earlier frozen artifacts are unchanged; future portable archives must retain
this correction. Expanded and old-corpus counts use separate denominators.

The old168-byte exp overlay overlaps the first14 bytes of the new table entry.
A local-byte-array negative loader preflight rejects that corruption. Source
merge/relink and checks of actual linked bank layout, overlay order and loader
bounds are mandatory. This private component does not establish integrated
size, universal stack, physical cycles, general-pow totality, whole507 or release.
