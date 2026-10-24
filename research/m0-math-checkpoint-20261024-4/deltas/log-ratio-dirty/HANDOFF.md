# Exact busy-divider log quotient: 8,283 observed speed deficits removed

Private RP2040-only diagnostic component. Replace the slow Q70 log
quotient's three software divisions with the existing log10 reciprocal,
an existing retained-product kernel and an exact three-bit remainder
correction. Add exact shift shortcuts at the two dyadic endpoints and a
busy-zero assembly return. The result remains floor(delta*2^29/den) for
the entire original domain. All callers and mathematical enclosures are
unchanged. No canonical runtime, device or firmware is modified.

Every denominator2049,2051,...4095 is checked with exact integer bounds.
The bare ARM check covers38,902 numerator/denominator pairs in both SIO
states:155,608 calls including independent product-seed calls. It loads
only the component and its184-byte product capsule, not firmware or ROM.
The capsule independently assembles byte-exact from the pinned source.
Every helper result equals unbounded integer floor division; ABI, SP,
bounded writes and zero SIO accesses are checked. Endpoint branches have
4,096 direct helper calls. Observed direct helper stack is68 bytes.

Public ln has14,907 unique inputs,29,814 fully profiled READY/DIRTY state
cases and119,256 actual ARM calls against the parent, frozen resident,
Qfplib and fresh MPFR4.2.2. All own/parent results are correct and raw NaN
policy matches. Caller SIO, PCS/SP and bounded writes pass every call.
The total qualification is274,864 ARM calls. Peak public stack remains
488 bytes. All14,907 READY counts are identical to the parent. DIRTY has
12,893 faster and2,014 equal cases, zero regressions. ln(2) falls from
1,250 to612 DIRTY instructions, versus Qfplib711.

Correct-Qfplib deficits in DIRTY fall8,310->27:8,283 state deficits fixed,
zero newly introduced. READY retains its original27. These are the same
27 raw inputs (54 state rows), consisting of IEEE zero/+Inf and normal
refinement paths. All ten historical ln deficits remain open in this
component. The expanded set, its remaining losses and every raw incorrect
Qfplib outcome are retained. This is a measured corpus, not exhaustive
binary64 performance or a whole-ln GO.

Only the slow helper changes in the CPP object,76->232 bytes, while the
other three functions in its shared section remain byte-identical. The
assembly busy-zero return adds8 bytes. Total object growth164 bytes;
linked component growth160 due to alignment. Existing tables, global RAM,
undefined dependencies and generic M0/M4 allocated controls are identical.
The table definition moves earlier in the RP translation unit and is
emitted once. The original READY assembly source prefix is unchanged.
CPP object, assembly object and entire diagnostic ELF independently
recompile/relink byte-exactly. No whole M4 firmware build is claimed.

Center source SHA256:9480f6ffa1abc80b502f35499b4d8b2fd1fdd42b3de0408af2feaadcd7be6d74.
Ratio ASM SHA256:30fd45e3489f1f09a45388915c18e7f0c93015033187969509260316480b48ce.
ELF SHA256:4e1a6b9151b96b5f9355e75c891c508809cad22d6c67fb9ef33354485acd5dff.
Full CPP object SHA256:2c3609d88f1bb99415de6cae03102adc2d340e2392fbef3e9f4b7570df191666.

Hold this source/evidence packet unchanged for inspection. Independent
review, integration and hardware acceptance are not claimed. Instruction
counts are not physical cycles. The original whole-math goal remains OPEN.
The next separate enclosure study is in.m0-ln-enclosure-20261024: exact
prospective RP bounds7.897373/3.685012 permit strict radii8/4 instead of
the old16/8; no runtime change from that study is included here.
