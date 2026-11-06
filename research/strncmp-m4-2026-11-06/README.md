# Classic F411 `strncmp`, 2026-11-06

Native/runtime winner: byte-only four-way unrolled kernel, 84 bytes, no stack or
helper calls. The installed baseline was 42 bytes. Every byte pair is guarded
by the remaining count; zero count touches neither input. The return value is
the exact unsigned-byte difference. `code/memory_strncmp_arm.h` has the same
SHA256 body as the measured `sn_byte4` in `candidates.S`:
`25557c04ff36ffb12d0e376c167a57018d15fdada1e9afa2a6d17cc044534276`.

Actual Classic F411 AEB505B6E0067623, 96 MHz, firmware6186AE4B plus separately
pinned diagnostic fixture35963eeb. Four routes: ordinary standalone and shared
SDK APPs, each with leaf code in SRAM or Flash. Each route has 3904 cases,
10 functions and seven retained DWT raw intervals: 15616 cases / 1093120 raw
intervals total. The public shared SDK tail really forwards through slot19 of
the unchanged26-entry runtime table. Its overhead is retained in its own data.

| Code / carrier | Byte4 / baseline geometric mean | Length<=8 | Worst median ratio |
| --- | ---: | ---: | ---: |
| SRAM / standalone | .747167 | .764338 | 1.000000 |
| Flash / standalone | .811889 | .830038 | 1.000000 |
| SRAM / shared | .747162 | .764338 | 1.000000 |
| Flash / shared | .811883 | .829976 | 1.000000 |

These compare equally placed leaf bodies in each route. No case median regressed
against the native42 clone. The Flash results give about19% lower geometric
mean time; SRAM about25%. They are not measured whole-application speedups.
The actual resident/runtime addresses and SDK tail are also recorded separately.
The autonomous SDK keeps newlib120: byte4 has slower long cases against it.
F401 keeps its C42 function and Flash reserve; M0 is unchanged.

The corpus covers SRAM/SRAM, SRAM/Flash, Flash/SRAM and Flash/Flash, zero count,
unsigned differences, NUL, matching prefixes, differences just outside n, short
and long strings up to512 bytes and SIZE_MAX. Hardware uses eight alignment
pairs. HOST semantic checks cover all16; no claim is made that16 were timed.
DWT is qualified against the public millisecond clock before every APP batch.
CONTROL=4 (privileged MSP, FPCA active), IPSR=PRIMASK=0; six clock/cache/FPU
context words are identical before/after each group. IRQs, clocks and cache
configuration were not changed for the measurement. All raw intervals include
the checked indirect-call loop, divided by the actual repeat count; no overhead
subtraction or sample removal. Min/median/max, bank, n, alignment, alias and all
seven raw values are retained in the full maps. Real application frequencies
are unknown; inverse-length weights in RESULTS.json are sensitivity models.

A USB read timed out before APP90 of the shared/Flash route. Its physical
receipt remains HOLD with the first error intact. Fresh read-only health passed;
a separately reviewed finite phase executed only previously unexecuted90..97.
No APP or case was replayed. Both process/descriptor closures were recorded.
`RESULTS.json` pins the explicit logical coverage index and complete local raw
analysis under `.build/strncmp-m4-20261106-v1` in the primary repository.

Production validation: `tests/strncmp_m4_self_test.py` compiles and executes the
real native body, unchanged standalone libc, M0 fallback and actual SDK tail
through runtime26/slot19. It checks exact input-read bounds, n0 unmapped inputs,
bounded unterminated buffers, all16 alignments/four banks, aliases, unsigned
results, stack and callee-saved registers. F401 C42 and M0 bodies are checked
against their unchanged controls. Guarded Unicorn is HOST semantic evidence;
its timing is not hardware evidence. Run with the pinned GNU Arm14.2.1 toolchain
using `--toolchain-bin` and a fresh `--output` directory. The existing native
libc sanitizer tests also pass. Full firmware and system APP budget results are
recorded with the final image separately; a change of build configuration is
never attributed to the42-byte function increase.


Final hardware integration passed on the ordinary working build99BEFCD2.
Fresh318e9d647 normal-profile builds have identical features (resident CHIP8,
resident SETUP): control400204 bytes, production400244 bytes. Native code grows
42 bytes; the complete linked image grows40. F411 free Flash124044 >=16384,
RAM globals22024, maximum frame1928 <=5120. F401 remains256964 bytes, free5180
>=4096 and C42 unchanged. The complete final System APP bundle fits20480.
The earlier388720-byte release-case build had different CHIP8/SETUP features;
that configuration was used only for HOST budget checks and was not installed.

The final actual APP checks the full512KiB CRC of the newly installed ordinary
prefix plus FF tail, the native84 bytes, actual runtime26 table/slot19 and the
relocated public12-byte SDK tail. It performs772 functional calls on all16
alignment pairs and four data-bank combinations, including n0 unmapped pointers
and alias SIZE_MAX. This is functional integration evidence, with no timing
claim. All own measurement files were byte-proved before any deletion; both
measurement directories and the final smoke directory are gone. Descriptor,
lock, PID, session, EXIT0, reap and no-holder closure are recorded in
`FINAL-HARDWARE.json`. The coordinator independently accepted CLOSED after verifying image, raw,
receipt, process and cleanup. The first cleanup guard HOLD remains
preserved and contained no deletion, firmware installation or APP execution.
