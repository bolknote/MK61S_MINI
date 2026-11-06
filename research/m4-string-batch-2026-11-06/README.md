# Classic M4 string kernels, measured 2026-11-06/07

The complete Classic F411 campaign passed: 34,848 cases across four APP/code
placements, 1,092 timed APP runs and 1,383,648 retained DWT intervals. Byte4 is
selected for native strnlen, strcpy, strncpy and strncat. The new 13A2194A
image is installed and its final 7,168 functional native/SDK/
runtime21 calls passed, including a full 512 KiB physical CRC check.

The target was Classic F411 UID AEB505B6E0067623, USB 2068336B4731,
classic-v3-uc1609, 96 MHz. The diagnostic image retained the exact ordinary
99BEFCD2 resident prefix and added measured leaves/data at 0x08062000. Four
real ABI6 APPs compared equally placed original C, byte2 and byte4, private
SDK/libc controls, actual resident functions and the real runtime26 slot21.
Input SRAM/Flash and code SRAM/Flash remain separate in the evidence. The
APP/runtime pointers, function bytes, entire table, CPU/IRQ/CONTROL and
RCC/Flash/cache context were checked before and after groups.

| Native function | Selected size | Time reduction: source SRAM / Flash |
| --- | ---: | ---: |
| strnlen | 54 B | 44.6% / 44.0% |
| strcpy | 46 B | 34.9% / 29.5% |
| strncpy | 126 B | 28.5% / 25.9% |
| strncat | 98 B | 42.7% / 40.1% |

These are reductions in the mean of per-case median measured loops against
the resident native control, with code in Flash. They are benchmark results,
not whole-calculator speedups. The shared-APP Flash series confirms the same
ranking. An inverse-work score, 1/(work+1), increases the weight of short
operations and also selects byte4 separately for every function/source bank.
This score is a synthetic model, not measured application frequency.

The regression map is explicit: empty strnlen with positive n costs 3 extra
cycles (about 10%), and empty strcpy costs 1 extra cycle (about 3.4%). Both byte2
and byte4 have these small costs. Every native-Flash short-work bucket still
improves under inverse-work scoring. Native-Flash strncpy and strncat have
no slower paired cases. Private SDK bodies are retained: the measurements
show why Flash code, SRAM code and SDK word loops cannot be assumed equal.

Each case retains all 7 raw intervals, min/median/max and repeats. No samples
were removed and no timer/call overhead was subtracted. Loops include indirect
calls and return-value checks; strncat includes resetting the original
terminator before each repetition. DWT was qualified against millis, and its
control/DEMCR restored in every APP. Distinct placements are reported apart.

Code commit 74a558435c3463045911005daef484006b13bfc8 contains the selected
instruction bodies. Source loads are individual bytes with exact NUL/count
stopping. strncpy writes exactly n bytes including zero padding; only its
aligned, bounded padding uses word stores. strncat additionally touches neither
pointer for n0. All 4 kernels use no stack/helpers. Default unroll4 is selected;
MK61_M4_STRING_BATCH_UNROLL=2 retains the comparison and
MK61_M4_STRING_BATCH_DISABLE=1 restores original C. F401/M0 fallbacks, private
SDK implementations and runtime26 ABI remain unchanged; slot21 reaches native
strncat without adding slots.

The single grouped HOST pass completed 81,130 ARM calls, all 16 source/dest
alignments, exact bounds/canaries/padding, ABI and actual SDK runtime tails.
The packed APP model checked all 8,712 C-generated keys against Python, four
profiles, partial writes, first-fault/replay handling and 53 CRC-repaired bad
reports. HOST ticks are synthetic, never hardware speed evidence. A targeted
recheck passed the actual initialization-kind4; the original model's unused
kind argument and its immutable evidence are documented in the artifacts.

Full F411 normal link: 400460 B, free 123828 >=16384; globals 22024, max frame 1928
<=5120. Sealed 13A2194A has byte-exact measured byte4 bodies, 16-byte aligned,
and the actual slot21 points to selected strncat. The feature-matched C build
has the same 4 bodies as physical 99BEFCD2. Its whole image differs by 37 bytes
after a build-date rollover, so whole-image identity is not claimed. Full
F401 product Classic V3: 256964 B, free 5180 >=4096, globals 29364, max frame 1312
<=2048; all 4 C bodies unchanged. Twenty System APPs (9 F411/11 F401) passed ABI6
header/payload CRC, production decode/relocations and unchanged 20 KiB memory
limits. F401 MARKDOWN 13589 B <=14336. The tightest APP has 12 B arena headroom;
no contract was weakened.

Evidence: /Users/bolk/Projects/MK61S_MINI/.build/m4-string-batch-20261106/.
HARDWARE.json pins selection, complete analysis, PER-CASE and REGRESSIONS.
Physical phases retain exact argv/grant/source hashes and PID/session/EXIT/
reap/FD/lock/holder closure. The latest direct user policy is no old-state or
firmware backup/restoration, no RTC operations and no cleanup just to restore
previous contents. No automation/timer was created. Foreign primary-checkout
WIP and Pico were not touched.

Coordinator independently accepted hardware CLOSED after the new-image check.
The installed image is 13A2194A; 7,168 logical functional calls include 2,688
real SDK runtime21 forwards. No device IO followed that final closure.
Exact candidate/SDK source pins are preserved in source-archive-001/ARCHIVE.json.
