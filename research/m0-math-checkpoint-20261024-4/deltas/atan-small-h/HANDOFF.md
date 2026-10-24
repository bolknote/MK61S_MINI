# atan small-h lower gate: no observed correct-Qfplib deficit

Private child of the sealed directional/ninth component. A tighter
one-sided enclosure for h<1/512 reuses the old polynomial and metadata.
It removes the last two observed correct-Qfplib speed deficits without
new tables, global RAM, dependencies or helper algorithms.

The full enlarged corpus has58,188 unique inputs and116,376 profiled
READY/DIRTY state cases:465,504 public ARM calls, zero own/parent errors
against fresh MPFR4.2.2, exact inherited NaN sign/payload policy, PCS/SP,
bounded writes and caller SIO preservation. All106,312 retained parent
instruction counts reproduce. The bare helper replays add75,298 calls:
540,802 actual ARM calls in this packet's qualification.

For107,542 state cases where Qfplib is correct,107,539 are faster and
three equal, zero slower. The final two raw inputs ±3FEF1BCDCF0D1830 now
cost1,787 DIRTY instructions, equal to Qfplib. BFABB0EDC0AE5C6F moves
from1,797 to1,804, also equal to Qfplib. The8,834 raw incorrect Qfplib
outcomes remain in the full report; they are not speed-equivalent answers.
Two raw inputs ±3F99C24957C90E1F still run CORE-MATH; Qfplib is wrong on
them. This is a result for the complete measured corpus, not exhaustive
performance over every binary64 input.

Versus the immediate parent,111,678 state cases are faster,4,566 equal,
132 slower by1-7 instructions. Versus V164,111,868 improve,4,504 are
equal and four regress (two raw inputs with incorrect Qfplib answers).
Every regression and raw output is retained. Stack remains912 bytes.
Only.text.atan_fast changes2040->2100 bytes: +60 code bytes, unchanged
helpers, tables, undefined dependencies and generic M0/M4 compile controls.
Full public object and entire diagnostic ELF independently recompile and
relink byte-exactly. No whole firmware or M4 rebuild is claimed.

Source SHA256:a85bbc49f2366ae64d025b36dfd27e86abf63c118e447cd43cedd060cdf87e2e.
ELF SHA256:fce98d75c6a88d57282b74798371c9c990029193741c4a986483a273321a50c9.
Full object SHA256:7fe226827039b3f6c63b58ad63b9940621924e07ec02a12e19ef9298b8ef9a55.

Independent review is not claimed. This source/evidence packet is held
unchanged for inspection. Counts are instructions, not physical cycles.
No canonical runtime, Git, device, firmware or prior checkpoint is changed
by this delta. The original whole-math goal, other operations, general pow
totality, repaired-base integration and hardware acceptance remain OPEN.
