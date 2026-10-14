# Primary writers of V: bounded ROM map

26 September 2026. Original IK1302 ROM; no native keyboard runs or emulator
state injection were made for this report. The accompanying checker proves
local connected suffixes, not their reachability from the current endpoint.

## Practical result

There **is** a short local writer of V that does not need a T or Y marker:

```text
46(Y) -> E5(Z: marker) -> E6(T) -> E8(U) -> E7(V) -> 47(W)
```

It writes the incoming 12-tetra A word only to numeric V, preserving every
other outgoing tetra on the suffix. In particular T, U, W and Q and all
service fields are untouched. The exact requirement is a **Z marker**.
Y is the marker for the four-word U/V/W/Q push, not for this single V write.

At the endpoint under investigation Z contains the only copy of `u`:

```text
P0=w; X/Y/Z/T=w/1/u/q;
Ms U/V/W/Q=v/m/a/p; upper=w/b/c/d;
markers=real,V.
```

Consequently this is not an immediately usable cleanup. Replacing Z with a
marker first requires reserving `u`, and after writing V the Z marker itself
still needs a preserving removal. Entry into 46(Y), the source A, and the
continuation after 47 are additional obligations. A phase adjustment alone
does not supply a Z marker.

## Complete primary inventory for the marker tetra

All 256 command words were expanded at microtick 22. The only physical
output emitters capable of changing the marker-test tetra M2[22] are:

| Family | What it writes | Relevance to the current V marker |
| --- | --- | --- |
| 32 | Nine low numeric tetras from A, including M22=R21 | Existing reset-entry analysis constrains every reachable 32 to the 00→32→34 chain, with A filled with F; this creates/retains F rather than clears it |
| C7 / E7 | Twelve-tetra A ↔ numeric-M2 exchange | C7 and E7 are identical local instructions; the existing completed controller abstraction has no C7 entry; E7 geometry is detailed below |
| A8 | Same numeric exchange, repeated until incoming S1=E | Ordinary four-word push cannot touch V without also touching T or W/Q; the single-A8 suffix has a useful local contract but needs a different entry context |
| E9 | Twelve-tetra A numeric write | In the marker-dispatched family target is marker+2: V requires T marker |
| BC | All fourteen B tetras to M2 | Locally marker-free, but **excluded for preserving initial V service 00** by the prior reset-reachable write-range invariant |

All except BC copy R21 into M22; BC copies R19. The checker proves these
exact sources. D4 writes M1 (ordinary-register lane), D6 only reads M1,
C9 writes M3, and 34/A3 affect numeric header tetras but **not M22**. Thus
none of those instructions can itself remove the V marker.

The exclusion of an independent useful 32 entry is the prior completed
analysis in [ms-header-repair-boundary.md](ms-header-repair-boundary.md), not
a new whole-controller run. The local writer inventory itself is rerun here.

## Exact marker-relative destinations

The new checker proves the following connected suffixes from E5 with a
matched marker. The selector and return-stack premises are explicit.

| Suffix | Target offset | Real marker | V marker | Z marker |
| --- | --- | --- | --- | --- |
| E5→E6→E7, S1=7 | +2 | X1 | Q | U |
| E5→E6→E8→E7, S1=8 | +3 | X | P7 | **V** |
| E5→E6→E9, S1=9 | +2 | X1 | Q | U |
| E5→E6→EE→A8→A9, S1=E, stack A8/93/... | +3 | X | P7 | **V** |

This explains why neither ordinary E7 formatting nor the single-A8 variant
automatically fixes the current real+V geometry. The short A8 reads
marker+2 and copies it to marker+3; it does not choose V merely because V
is the unwanted marker. These are primary prefix contracts only; arbitrary
return contexts in this table are not asserted to be keyboard-reachable.

## The two other local alternatives

### Single A8 after reading U

The standalone suffix

```text
EE(U) -> A8(V) -> A9(W) -> 93(Q)
```

with initial S1=E, R35=E and address stack A8/93/E5 copies U to V and changes
no other output field. A9 alters two header tetras of the displaced V in
internal A; that is harmless only if V is a disposable marker. This suffix
does not inspect any marker, but its entry has **not** been constructed at
the current endpoint. Via the regular E5/E6 path it again needs a Z marker.
The old-address-return mechanism exists elsewhere in the historical study
([a8-single-entry.md](a8-single-entry.md)); that is not a license to assume
the required stack/phase here.

The normal E7+three-A8 four-word push and the 60+eight-A8 block cannot have a
footprint containing V but excluding T, W and Q: any contiguous four-or-more
word interval containing V includes at least one of those neighbors. That
is an obstacle to a *single local preserving block*, not a prohibition on
longer permutations or restoration from saved copies. Odd-S1 A8 never exits
by its S1+=2 test and is not a finite cleanup by itself.

### BB(U)→BC(V): excluded when original V service is 00

The checker proves the connected two-command store independently: BB writes
nothing; BC copies all 14 initial B tetras into physical V and returns via
the address stack. No T/Y/Z marker is needed in that suffix. This is a real
different writer family, not an E7/E9 alias.

That arbitrary-state local contract does **not** leave a preparation problem
open for a V whose original service byte is 00. The already completed
reset-reachable audit proves a stronger restriction:

```text
every BC output service byte M2[40]:M2[37] is in {A3, AF, F0..FF};
no other instruction on any of the three installed chips writes either tetra.
```

Thus BC cannot preserve service 00 at that write. Nor can it overwrite it
temporarily and restore 00 later: every later writer also produces a member
of that nonzero set, and plain circulation only transports the same service
tetra tokens without changing them or moving another lane into their place.
After first writing a 00 service pair, its byte cannot be 00 again in the
covered model. Consequently **any BC(V) excludes the original all-service
preservation contract if V's original service is 00**, regardless of whether
its numeric payload would be useful or a keyboard entry could be found.

This uses the prior audit in [c8-cc-bc-bound.md](c8-cc-bc-bound.md), covering
52,416 abstract states, 95,731 edges and all 38 incoming BC edges, and the
[independent review](k2-independent-review.md). The graph and the all-chip
service-writer proof were **not rerun** for this report. The new checker adds
only a small inductive set lemma, explicitly accepting those established
facts as premises. Actual verification that the current fixture's original
V service equals 00 remains the native fixture check, not this symbolic map.

The restriction requires the same digital-reset history and unchanged
IK1302/03/06 model as the prior audit. An arbitrarily injected processor
state with arbitrary B is outside that theorem; its local BB→BC equality is
why the unconstrained symbolic store contract can still pass. For original
service values inside the allowed set, this particular 00 corollary says
nothing about whether the other preservation and entry obligations can be met.

## Reproduction and limits

```sh
python3 tmp/ms-rom-reachability/k1-v-writer-map-check.py
```

Result: PASS for the complete primary M22-emitter inventory, exact
46→single-E7(V), standalone EE→single-A8(V), twelve marker-relative suffixes,
BB→BC(V), and the conditional zero-service set corollary. This run does not
audit the other two chips' writers, reprove the prior BC range theorem, prove
native keyboard entry, cover concurrent writes, or prove a completed exit.
The useful near-term consequence is to distinguish **save u then Z-marker
single writer** from the already-known **save q then T-marker E9** strategy.
