# Directional residual and short ninth-order atan repair

Private RP2040-only child of the reviewed geometry component. It adds
rounded residual correction, bounds using the exact division remainders,
a short Q16 ninth-order term, and a low64 inverted-residue predicate.
The original ambiguous-case refinement remains. This is an intermediate
author result with two observed speed inputs still open; independent
review and production integration are not claimed.

All 53,156 unique inputs are profiled in both READY and DIRTY states:
106,312 public state cases and 425,248 actual ARM calls. Fresh MPFR4.2.2
finds zero own or parent errors, including the inherited raw NaN policy.
The original 79,096 parent instruction counts reproduce exactly. Bare
helper checks add 75,298 ARM calls against exact unbounded rational
references, for 500,546 calls in this packet's qualification.

All seventeen previously observed raw Qfplib deficits are now faster in
both states. The larger corpus contains twenty raw parent deficits and
two candidate deficits: eighteen are resolved, none newly introduced.
The remaining raw inputs are 3FEF1BCDCF0D1830 and BFEF1BCDCF0D1830.
Their DIRTY costs are 22,764/22,763 instructions versus correct Qfplib
1,787; the inherited CORE-MATH refinement still runs. Every raw output,
including 8,272 incorrect Qfplib state outcomes, remains in the report.
`remaining-slower.json` preserves all four open state rows.

Versus the geometry parent, 101,748 state cases improve, 4,504 are equal
and 60 regress by 17-267 instructions. Versus frozen V164, 101,800 improve,
4,504 are equal and eight regress (four raw inputs, +237/+263). The
complete regressions are retained. These are executed instructions, not
physical cycles or a whole-library speed claim.

The change adds 400 allocated code bytes versus its geometry parent,
with no new table, global RAM or libgcc dependency. Peak observed public
stack is 912 bytes versus 888 parent. Generic M0 and M4 soft/hard allocated
compile controls match. Other allocated sections, tables and undefined
dependencies are unchanged. An independent producer invocation recompiles
the full public object and relinks the entire diagnostic ELF byte-exactly;
this is reproducibility evidence, not independent human/agent review.

The residual, inverted predicate and inline-source ninth wrapper execute
without firmware or ROM mapped. The public function also uses pinned
resident runtime helpers and captured ROM support; no ROM mathematical
entry is introduced. All calls check PCS, SP, bounded writes and SIO.
The standalone inline-source wrapper has separate register allocation
from the public caller, which is profiled separately.

Source SHA256: 996dcd240df881b6592b61aeca95fd446c7522b6fff71bc1c6de8eeed9001d23.
Component ELF SHA256: 35247afa5324a99d061028c606b495a5cd2ccf4bb778a62949d285cf32d99b0a.
Full object SHA256: 69095e178c6a559c812fc7528143515387456264e72cc509cbae8fc728f3bbe7.

`PROOF.md`, `certificate.json`, helper contracts, all-input qualification,
isolation and public-byte binding describe the exact scope. Canonical
runtime and devices are unchanged. The full math goal, other operations,
general pow totality, combined-image integration and physical acceptance
remain open. Hold this source/evidence packet unchanged after sealing.
