# real/Y/T: which ordinary request can reserve u?

26 September 2026. Bounded structural analysis of the unchanged IK1302 ROM.
No new keyboard trials, phase enumeration or native-state injection were
performed for this map. The root agent independently verified the supplied
entry on two native keyboard fixtures and compared unobserved full states.

## Entry and conclusion

The entry in `k1-y-t-entry.cjs` has:

```text
X1=q; X=v, Y=m, Z=q, T=m;
Ms U=v, V=u, W=q, Q=p; upper=a/b/c/d; P0=w;
markers=real,Y,T.
```

All 23 original numbers are in stored words. In particular `u` has its only
stored copy in V, while `w` has its only stored copy in ordinary P0. The
desired next step is a preserving reservation of `u`, ideally with X=u,
before placing another marker in V.

**These four ordinary requests have not supplied that reservation.** The
early and late reads checked below never read V. RCL0 and the observed
ENTER family instead put a different number into V during formatting. Two
LastX families were resolved through their second EE; one writes an upper
four-word block and the other formats a copied marker, not `u`. The latter
anomalous formatter is not analysed to completion here, so this is not a
whole-command impossibility theorem for every LastX continuation.

## Only three accepted-control origins belong to this scanner

The exact local rule is `9B -> 9C iff M22=F`; otherwise 9B repeats. With
markers real/Y/T, 9C can therefore occur only at **control, Z, or U**. An
arbitrary-origin map with 9C at another physical word would not describe this
scanner geometry.

Each table row assumes that its 9C is accepted:

```text
M34 >= (M31 == F ? 1 : 7).
```

The checker explicitly asserts that predicate and the pending opcode. It
does not claim each accepted origin is selectable with a particular delay
in the current native fixture. It makes no change to the scanner state.

## Exact early map

| Request | Accepted 9C at control | Accepted 9C at Z or U |
| --- | --- | --- |
| ENTER, 0E | EE reads U=v, returns E0 | EE reads X=v, returns E0 |
| LastX, 0F | EE reads T=m, returns F0 | EE reads X1=q, returns F0 |
| RCL0, 60 | First EE reads W=q; then D6 reads M1(U)=P0=w | First EE reads X=v; then D6 reads M1(U)=P0=w |
| STORE0, 40 | EE reads W=q; D4 copies q to M1(U)=P0 | EE reads X=v; D4 copies v to M1(U)=P0 |

All twelve prefixes are connected symbolic executions, not separate
compatible edges. Before the terminal read there are no ring writes.
STORE0's sole write in its proved prefix is the exact twelve-tetra M1
numeric write; M2, M3 and service fields are held. D4 returns A5; D6 returns
A7. The early EE in RCL0 is not the number ultimately loaded: D6 replaces
the internal A with the ordinary register's word.

STORE0 is unsuitable at this entry because it overwrites the sole stored
`w` in P0 before making a reservation of `u`. This is a failure of the
stored-word preservation contract, not a claim that every internal processor
tetra containing any fragment of `w` has been erased.

## Two LastX continuations

The checker follows each of the three origins through its second EE and
checks every primary output tetra in between. No E9/A3 repair is assumed.

### Accepted control: copy a marker to X, not u

```text
EE(T=m) -> F0(U) -> E0(V) -> A7(W)
-> E5(Q/P7/P8/P9/P10/real)
-> E6(control) -> E8(X1) -> E7(X)
-> A8(Y/Z/T) -> A9(U) -> E1(V)
-> ... -> E2(T) -> E5(U/.../real)
-> E6(control) -> ED(X1) -> EE(X=m) -> E3
```

The sole write block is visible X/Y/Z/T, leaving:

```text
X=m, Y=v, Z=m, T=q; every Ms word unchanged.
```

The late reader skips the marker in Z because its scan begins at U; it
reaches real and reads X. Thus the tempting inference “a Z marker now
exists, so this LastX will read V” is false for this actual continuation.
The later noncanonical formatter of X=m is outside this proof.

### Accepted Z or U: four-word write in W/Q/P7/P8

```text
EE(X1=q) -> F0(X) -> E0(Y) -> A7(Z)
-> E5(T) -> E6(U) -> E8(V) -> E7(W)
-> A8(Q/P7/P8) -> A9(P9) -> E1(P10)
-> ... -> E2(P8) -> E5(P9/P10/real)
-> E6(control) -> ED(X1) -> EE(X=v) -> E3
```

This produces:

```text
W=q, Q=q, P7=p, P8=a.
```

Old P8=`b` is displaced from storage into A; A9 then changes its two high
exponent fields. It is not a preserving stored-word reservation. The visible
stack remains unchanged, and V=`u` is not read. This is why merely selecting
the other accepted-control family does not turn LastX into a useful V read.

## RCL0 continuation and the known ENTER loss

For all three accepted origins, RCL0 converges on:

```text
D6(U: M1=P0=w) -> A7(V)
-> E5(W/Q/P7/P8/P9/P10/real)
-> E6(control) -> E8(X1) -> E7(X)
-> A8(Y/Z/T) -> A9(U) -> AC(V)
-> E2(W) -> E5(Q/.../real)
-> E6(control) -> ED(X1) -> EE(X=w) -> E3
```

It preserves stored Ms through that prefix and leaves visible
`w/v/m/q`, hence real/Z markers. It does not read V. A separate connected
canonical-formatting proof uses the current default `w=-7.654321E-23`
(class 1) and proves the subsequent numeric write is **X→V**. That replaces
the sole `u` with `w`; it does not reserve `u` first.

The same local formatter with class 0 proves X→V for current
`v=-9.8765432E-17`, matching the root agent's already observed ENTER
control-family negative test: U is read, visible stack is pushed, and late
X formatting replaces V. The complete ENTER continuation for the two other
accepted origins was not added here; their early reads are already covered
by the table. No extrapolation to all numeric classes is intended.

## What remains open

The obstruction is now positional: the ordinary readers skip V, while a
normal visible push moves the Y marker to Z and directs the default late
formatter into V. A useful next construction must first reserve V, or move
`u` into a readable position without making V disposable too early.

A secondary operation such as ↔ or F-comma is a separate family worth
analysing for that rearrangement. **No preserving such continuation is
claimed here.** The table also does not exclude a longer composition, a
different command, or a different marker geometry.

## Reproduction

```sh
python3 tmp/ms-rom-reachability/k1-y-t-read-map-check.py
```

PASS: 12 early prefixes, 6 LastX/RCL0 continuations through their second EE,
the marker-scanner rule, and two separate canonical late formatter cases.
The native integration and effects of concurrent chips remain independent
obligations; README and the root agent's entry checker were not modified.
