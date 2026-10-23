# atan: faster enclosure and output packing, remaining cases retained

Original CPU math goal, private RP2040-only delta over immutable V164.
One source include changes. It reuses the known output binades instead of
the general96-bit packer and applies proven one-sided Newton error bounds.
The argument geometry, reciprocal, polynomial, tables and fallback stay.

The two historical atan deficits now beat correct Qfplib:

| Input | READY candidate / V164 / Qfplib | DIRTY candidate / V164 / Qfplib |
|---|---|---|
|`3FB97996F4E5F9F0`|1362 /3066 /1796|1548 /3942 /1796|
|`BFDD440162570130`|1304 /3041 /1796|1470 /3914 /1796|

The existing reference is `audit_atan`, Qfplib's atan2(x,1) composition,
exactly as in the historical comparison. These are executed instructions,
not physical cycles. The original507-input matrix is unchanged.

29,138 distinct binary64 inputs are tested in both READY and DIRTY states:
58,276 public cases /199,772 actual ARM calls, with directed MPFR4.2.2.
There are zero candidate/parent rounding errors. Raw NaN sign/payload bits
match the parent on every call. All wrong Qfplib outputs remain in the
data:2737 per state, rather than being called valid speed comparisons.

24,944 cases are profiled:24,498 faster than V164 /446 equal /0 slower.
On the correct-reference subsets, READY deficits reduce18->4 and DIRTY
286->4. There are zero new deficits versus correct Qfplib. Every profiled
rebuilt-control result/count equals its original resident counterpart.
Unprofiled rows support correctness only.

**atan is not finished.** The expanded corpus finds four remaining inputs
in each state (two magnitudes, both signs):

- `3FE5D1004FC925B6`, `BFE5D1004FC925B6`;
- `3FECB99548F4FA32`, `BFECB99548F4FA32`.

Their preserved rows are in `remaining-slower.json`; they still reach
CORE-MATH and cost about20,900-21,100 READY instructions versus1783-1791.
They were already slower in V164. This is a useful optimization delta,
not a claim that every atan input now matches Qfplib speed.

The exact-rational certificate retains the parent's458,752 selector
endpoint checks and proves all directional/regional enclosures. The
unchanged reciprocal/ratio is additionally executed147,456 times over
65,536 seed bucket endpoints and random denominators in both SIO states;
its one-sided bounds hold. All65 unchanged atan table rows are independently
enclosed within1/2 Q70 using directed256-bit MPFR.

Full public object audit: only `.text.atan_fast` changes,1744->1648 bytes
(-96), no new allocated section/table/global RAM or dependency. The rebuilt
parent matches all259,764 allocated bytes of the original frozen object.
Independent public reassembly/relink reproduces the entire executed ELF
byte-for-byte, without excluded instructions. The existing780-byte atan
table is identical. Generic M0 matches247,584 allocated bytes; M4 soft/hard
compile controls match (this source is off-target there, not a whole-M4
firmware rebuild).

The numerical component executes with pinned resident helpers and captured
ROM. It is not a bare standalone firmware. DIRTY SIO is preserved exactly;
the unchanged parent math divider may use an idle READY divider and must
leave it clean. Callee-saved registers, SP and bounded writes are checked
on every call. Observed maximum stack872 versus880 bytes for the parent.

Current source `native_eabi_m0_atan_fast.inc` SHA256
`502deb2e33c2736eb7d7f672e250a61c716e616362a8574ad1367620bc7ae541`.
Full public object SHA256
`fe74189c9165e4d9378b4a182130fdb24f827579896a34f3ec43d5372333366e`.
Executed component ELF SHA256
`93830c121ef76ccc3278233bd54b4ed2a5f2a4313a466d8854115c097f02f946`.

Integration patch: `atan-packing-only.patch`. Reasoning: `PROOF.md` and
`certificate.json`. Actual evidence: `qualification.json`,
`reciprocal-proof.json`, `table-proof.json`, `isolation.json`,
`public-body-proof.json`. Initial higher-overhead/symmetric trials are
historical; their reports retain their own source/ELF hashes.

Independent review is pending. No canonical/frozen source, Git, USB or
Flash change; no firmware/version or extra platform pipeline. Whole
library speed, total general pow, repaired-base integration, physical
timings and hardware acceptance remain open. The goal stays active.
