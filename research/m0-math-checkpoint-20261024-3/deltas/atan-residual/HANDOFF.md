# atan: four confirmed residual-repair wins, eleven observed deficits open

Private RP2040-only delta over the immutable accepted atan packing stage.
No canonical math/platform source, Git, USB, Flash or firmware was changed.
The earlier human checkpoint9859eeae7 remains unchanged.

All four previously retained speed inputs are now faster than correct
Qfplib in both SIO states, with the exact same binary64 answers:

| Input magnitude | READY | DIRTY | Qfplib positive / negative |
|---|---:|---:|---:|
|`3FE5D1004FC925B6`|1568|1750|1784 /1791|
|`3FECB99548F4FA32`|1555|1725|1783 /1790|

The previous parent took20,861-21,103 instructions READY and22,288-22,486
DIRTY on these inputs. The candidate reuses exact reduction geometry,
computes a signed71-bit residual and uses a bounded six-bit Thumb divider.
The angle interval remains strictly below6 Q70 units; undecided rounding
keeps the original fallback. No approximation table, global RAM or libgcc
dependency is added.

The fresh full replay covers32,708 unique inputs /65,416 public state
cases /228,332 actual ARM calls, with MPFR4.2.2 and zero own errors.
The helper adds30,408 actual ARM calls against unbounded Fraction and
exact Python division, covering quotient magnitudes0..33, carries, ABI,
bounded writes and strict preservation of both SIO states.

The full functional corpus also exposed CORE routes outside the old speed
subset. A further176 ARM calls measure every one of those routes. The
combined32,124 distinct measured state cases retain **eleven preexisting
raw speed deficits** (22 state rows) against correct Qfplib; they are
listed in `speed-proof.json`. Do not report zero overall atan deficits.
Raw incorrect Qfplib outcomes are retained. `NEXT.md` records the next
geometry and polynomial work; it is not an implemented improvement.

There is a measured tradeoff against the accepted parent: ordinary paths
mostly add5-6 instructions; all additions are1-10 instructions. Across
the combined profile,12 cases improve,520 are equal and31,592 slow down
versus that parent. Versus V164,31,628 improve,496 are equal and none
slow down. These are instruction counts, not physical cycle measurements.
Observed stack writes peak at888 bytes versus872 for the accepted parent.

The full object changes only `.text.atan_fast` (1648->1748 bytes) and
adds the344-byte cold helper: net+444 bytes. All other allocated sections,
tables and undefined dependencies match. Generic M0's247,584 allocated
bytes match; M4 soft/hard off-target contributions match. This is not a
whole M4 firmware rebuild. An independent public recompile/relink matches
the entire executed ELF byte-for-byte, without exclusions. Resident
helpers and captured ROM support are pinned; ROM math is not used.

Source SHA256 `aa6ce7be864f7f364e106711d7173f66b78f1fe512f29779e7793dd99835c517`.
Component ELF SHA256 `f7c4c88bd931f48b97e361528d9d9fa78301a2eaf8a0165d543f6c0d49c49a35`.
Full object SHA256 `163cfa097f5df1a28b6d62dba7bd927d7c7ebf0aa11327ceafd369b90182f02e`.
`residual-only.patch`, `PROOF.md`, `certificate.json`, `qualification.json`,
`cold-profile.json`, `speed-proof.json`, `helper-proof.json`,
`isolation.json`, `public-body-proof.json` and `input-pins.json` bind the
source, proof and actual execution. Historical trials are not current data.

Independent review is not claimed. Hold this packet immutable for technical
inspection. It does not integrate the math onto the repaired Pico base or
qualify a combined image. Remaining atan inputs, pow totality and the other
required function deficits, integration, whole-image and hardware checks
keep the original complete math goal open.
