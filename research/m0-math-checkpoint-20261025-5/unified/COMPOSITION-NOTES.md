# Private unified source, phase1

Near-one CPP and table-product CPP differ textually only by the two near-one
exp additions. Their included pow-fast headers also differ: three pow calls
select the table entry instead of the older generic product. Whole CPP object
equality to near-one is consequently the wrong comparator. The first host
attempt also expected a nonexistent -cpp object suffix; those two host-only
preflight scripts/logs are preserved and made no ARM/MPFR call.

The composed source is near-one CPP with all core ASM/includes from the
qualified table-product candidate. Eight RP/defaultM0/M4 objects compile.
For RP CPP, all allocated bytes match near-one; the complete section/symbol/
semantic-relocation composition takes the three exp sections from near-one
and every other entry from table-product. This includes exactly three pow
call relocation changes. Core ASM matches table-product; all defaultM0/M4
objects match their qualified inputs. No arbitrary union of differences.

Next compose complete RP-native/root/exact-square/boundary/reciprocal sources
with real symbols, then link one private ELF. None of the required actual
linked R12/consumer/veneer, loader/layout, old168B-overlay14B corruption,
scratch4080, Flash/RAM/stack or whole507 gates has passed yet. Do not load
old diagnostic images over the new code. Canonical code/devices untouched.
This directory is mutable work in progress; historical frozen producers
were not executed. Runtime qualification begins only after source/link.
