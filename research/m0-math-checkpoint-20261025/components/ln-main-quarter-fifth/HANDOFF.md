# Private main-ln fourth/fifth coefficient gate

The RP2040 main packer now uses exact fourth/fifth coefficient remainders,
one-sided denominator bands and the exact n/2 ln2 error. Cheaper k=0 gates
use one-sided polynomial bounds first. Existing argument helpers, polynomial,
tables, near-Q77, fallback and generic-M0/M4 controls remain unchanged.
See PROOF.md, exact rational certificate and literal bare-unit source.

Fresh88589inputs/177178fullyprofiledstates/708712publicARM:0wrong MPFR4.2.2,
rawNaN/PCS/SP/boundedwrites/SIO pass; all120988parentcounts reproduce.
Bare120256ARM, including13940pack calls and13940rational endpoint checks;
2880new-predicate forced pack configurations, all normal n magnitudes,
coefficient signs/remainders/band/equality/midpoint/parity/carry controls.
No firmware/ROM in bare tests;0SIO accesses. Qualified828968ARM total;
probe, model and inherited calls are excluded.

Expanded14raw→5raw/10states,9fixed0new. All7earlier endpoint-probe losses
fixed; the larger corpus exposes seven more preexisting parent deficits,
two also fixed. Remaining5raw are retained without a whole-ln speed claim.
Of177178states,7398faster/84176equal/85604slower than parent. All parent
regressions retained, mostly+1..7instructions, maximum+108 on a preexisting
fallback path. Stack648vs640 (+8), bare72. Only2function bodies grow:
raw+376B, exact+512B; object/linked+888B, no newtable/RAM/libgcc.
Q77near and all other object/table bytes exact; genericM0/M4 allocated
controls equal. FullCPP/ASM/ELF and bareunit rebuild byteexact.

3FEC7001FFFFFFC1 READY694/DIRTY775 vsQfp783, parent2263/2344.
Three positive upper-point losses now READY602/DIRTY659 vsQfp785..824.
These are instruction counts, not physical cycles.

Source:4db4753b23ebaa7a17aed662d2f59d6b351f6c0d8739559ad4235e6c615f1fd2
ELF:2c0d376fe0b12c99f694279c2382977b00001875b4777aed504c0e1e309df728
Object:914f84aba1c288654cb604cc830873e6c059859c20b74784fbeba8b692e0b820

Freeze this inspection packet. Independent review, integration, physical
acceptance and whole-library/whole-goal GO remain open. Historicalauthor
302/507 and reviewed298/507 stay unchanged. Pow totality and other needed
operations remain in the original goal. No canonical/Git/device actions.
