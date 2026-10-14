# K× with real + V markers: two entry families, no E9(V)

This is a conditional structural result for the unchanged IK1302 ROM, not a
keyboard-phase search and not a general impossibility result for K1.

## State in scope

The native `NOP → RCL0` continuation has the following relevant endpoint:

```
ordinary P0 = w
Ms: U=v, V=m, W=a, Q=p; P7=w, P8=b, P9=c, P10=d
visible: X1=INV0, X=w, Y=1, Z=u, T=q
```

Only the real marker and V are markers. In particular, T no longer is one.
The old upper value `a` now has its only stored copy in W; `w` is duplicated
in ordinary P0, upper P7 and visible X. All 23 original values are present
before the tested continuation.

Physical order, in the notation used below:

```
marker control X1 X Y Z T U V W Q P7 P8 P9 P10
```

## Proven primary prefix

The companion `k1-single-v-neutral-map-check.py` uses the exact symbolic
42-tick IK1302 model. It starts at an accepted primary 9C, with pending
opcode 28 (`R30=8`, `R33=2`), and markers exactly at `marker` and `V`.
The accepted-9C predicate is

```
M34 >= (M31 == F ? 1 : 7)
```

All 15 possible physical positions of this accepted 9C were checked. Every
case has a satisfiable premise; the asserted contracts have no symbolic
counterexample. Other fields and keyboard signals are unconstrained except
for these premises. The possible continuations through A3 are exactly:

| Accepted 9C is at | EE reads | E9 writes | A3 writes request 28 into |
| --- | --- | --- | --- |
| Z, T, U, V, W, Q, P7 | X | Q | control |
| marker, control, X1, X, Y, P8, P9, P10 | P7 | X1 | W |

E9 copies the whole 12-tetra numeric word. A3 writes only numeric positions
28, 31 and 34: source position 28, then 8, then 2. Every other ring output
in this prefix is unchanged; A3 returns to D3. In particular, neither V nor
T is changed by this prefix.

The proof starts at an **accepted** 9C. It does not assert that each of the
15 origins can be selected by a keyboard delay with the particular fixture.

### Why the desired target is missing

After EE(X), A1 is at Y, and the marker scan runs from Z. With only real+V,
the first marker is V:

```
EE(X) → A1(Y) → E5(Z) → E5(T) → E5(U) → E5(V)
      → E6(W) → E9(Q)
```

Thus the read is already the desired visible X, but its destination is Q,
not V. E9 is two physical words after the marker that ended this scan.
For this same path to write V, T must be a marker when that scan reaches it:

```
EE(X) → A1(Y) → E5(Z) → E5(T) → E6(U) → E9(V)
```

In the other family, EE(P7) is followed by A1(P8); the scan instead reaches
the real marker, hence E9(X1). Changing only the accepted-9C phase while
keeping the real+V geometry cannot give E9(V).

## Consequence at the current endpoint

The first family copies `w` from X over `p` in Q. The second preserves Q
and reserves `w` in X1, but places the 28 request in W, damaging the only
stored copy of `a`. Neither is the desired preserving cleanup prefix.
This statement concerns the stored values and the prefix through A3; the
proof does not model a later secondary/numeric return or rule out recovery
by a different construction.

The parent agent's native full trace for the current no-extra-delay K×
matches the first family:

```
791300  9C at W=a → 9E
791309  EE reads X=w → A1
791316  E9 writes Q=w
791322  A3 writes control=287000000000
791339  later EE reads X=w → E3
791392  E7 writes P7=w (already w)
```

The parent reports that original `p` is absent at completion. This native
trace is independent evidence supplied by the parent, not produced by the
symbolic checker. No additional native phases were run for this report.

## Useful next constraint

The missing ingredient is not a phase that makes EE read X: that already
happens. It is a preserving way to retain or recreate the T marker at the
A1/E5 scan, or a different writer/marker geometry. Recreating T must first
protect `q`, which currently lives there. Alternatively, exploiting the
second family must first protect `a` in W and then handle its later return.
The existing `k1-single-v-store-map.md` gives a separate conditional STORE
prefix for saving visible X into ordinary P0; its proof ends at A5 and does
not establish that the later formatter leaves every Ms word unchanged.

These are precise outstanding constraints, not a proof that a complete
unchanged-ROM exchange is impossible.
