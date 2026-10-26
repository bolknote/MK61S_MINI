# Near-ln directional remainder gate

Private RP2040 child of the frozen strict-enclosure component. Reuse the
exact polynomial division remainders and signed h residual to shrink the
one-sided error interval. All polynomial/table/helper algorithms remain.

Fresh32940 unique inputs/65880 fully profiled READY/DIRTY state cases:
263520 public ARM calls, zero own errors against fresh MPFR4.2.2.
All39318 retained parent counts reproduce. Caller SIO/PCS/SP/bounded
writes and exact raw parent NaN policy pass. The exact inline packer adds
16896 bare ARM calls and11554 Fraction RNE endpoint checks without any
firmware or ROM mapped. Qualification total280416 calls; a discarded
invalid-neighbor test-generator run is not counted.

Of the old34 raw losses,15 are removed, including one more historical
ln input:2158->604 DIRTY instructions versus correct Qfplib800. The larger
corpus has parent89READY/95DIRTY losses and candidate45READY/51DIRTY:
44 expanded raw inputs fixed, zero newly introduced correct-Qfplib losses.
51 raw/96 state losses remain. All incorrect Qfplib answers,
remaining losses and regressions are retained. Historical ln now6/10
fixed and4 open; expanded inputs overlap and are not added to that count.

Versus parent: {'equal': 27402, 'slower': 38174, 'faster': 304}. Regression range7..105
instructions. Candidate stack640 versus parent600 on this same expanded
corpus; previous568 concerned a smaller corpus. Code+248 bytes, only
ln_near_interval912->1160. No new tables/RAM/libgcc/dependencies. Generic
M0 and guarded M4 controls match; this is not a whole M4 image rebuild.
Entire public CPP/ASM/ELF producer rebuild is byte-exact. Public calls use
pinned resident helpers/support ROM; no new math ROM calls are added.

Source:ba084abda5a2c3d71071ae800224c552efce2652d2838735782cd16e764b090e
ELF:272ecb817c396bd655cb19132f4df97c4d5d9da6046dc999a94a164de55e4425
Object:7795f4498c00ee28ac73dcd61b11a1952979a71b0f9113f72eb4ab6623e59f22

Hold this packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. The full math
goal, other operations, general pow totality and integration remain OPEN.
