# Local raw-writer alternatives to return 46

All entries below are **conditional symbolic ROM contracts**, not native
keyboard witnesses. Only the original primary ROM is read; no emulator state,
IP, register or memory setters and no ROM edits are used. Future serial data
and per-tick physical key pins are arbitrary conservative inputs. M2 denotes
the primary serial lane, not an independently chosen physical Ms destination.

The executable proofs are `cache46-writer-audit.py` (all 256 ROM words) and
`cache46-writer-contracts.py` (source-driven contracts and paired dataflow).

## Exact writer inventory

| Primary IP | Outgoing M2 indices | Source | Effect on A |
|---|---|---|---|
| 32 | 1,4,…,25 | A0…A8 | All A12 held |
| 34, A3 | 28,31,34 | A9…A11 | All A12 held |
| A8, C7, E7 | 1,4,…,34 | A0…A11 | Displaced M2 becomes A12 |
| E9 | 1,4,…,34 | A0…A11 | All A12 held; old M2 not retained |
| BC | 1,4,…,40 | S,B0…B12 | All A12 held; old M2 not retained |

There are no other primary M2 writers. For all eight writer words the inventory
checks every outgoing tetra against its old value under arbitrary state and
keys. `32` writes all six reader-cache tetras (old R0,3,9,12,18,21) into M2
indices **1,4,10,13,19,22**, despite writing only nine A tetras. Its next IP is
always 34; 34 stores upper three A tetras into the **next physical serial word**
and calls E2. This is not one aligned twelve-tetra word store.

## Entry 46 and destructive return 47

`46→E5*→E6→E8→E7→47` preserves arbitrary A12 before the E7. The 46 command
pushes 47, sets S1=8, and preserves numeric ST; E5 waits for M22=F without
changing A12, ST, S1 or return. E7 writes precisely A12 and loads displaced
M2 into A12. It does **not** place a backup of displaced M2 in B, C or ST.

At 47, A12 is replaced by the old first numeric ST lane. Each numeric ST trio
rotates `(x,y,z)→(y,z,x)`. The next IP is 49, the address stack is unchanged,
and the ring is not written. A saved prewriter A in ST can therefore survive
this path; the newly displaced M2 cannot survive there without an independent
earlier reservation.

The exact pair theorem uses executions with identical initial primary state
except for the twelve incoming M2 tetras at C7/E7, identical physical key pins,
and identical future serial inputs. Before 47 only A12 differs. After 47 the
**whole primary state and every emitted tetra are identical**. The same theorem
for an arbitrary pair of incoming A12 at 47 proves complete local discard.
This excludes a lossless local exchange, not other-chip copies, prior backups,
alternative return tags, or a full K2 implementation.

The only non-stack-return predecessors of 46 among all 256 ROM words are
**42, 43, A3**. A3 is the arbitrary-vector path and already stores upper three
A tetras. For 42, `R21≠0` forces 46 while holding A12 and pushing 43. For 43,
every A tetra is zeroed: it preserves the six cache fields only if all six
were zero already. The preceding 41 selects 43 exactly when A0…A7 are all
zero; that is not a constructor for six opaque payload tetras.

## Minimal alternatives without 46

| Conditional input | Path | Local result / missing condition |
|---|---|---|
| A source at CD, S1=7, arbitrary original top T | CD→C7→T | Exact A12/M2 exchange; displaced word stays in A at T |
| A source at E6, S1=7, original top T | E6→E7→T | Same exchange, no 46 or newly pushed 47 |
| A source at E8, original top T | E8→E7→T | Same exchange |
| A source at A1 | A1→E5*→E6→E9→A2 | One exact A12 store, original A held; old M2 overwritten without a backup |
| A source at E0 | E0→A7→E5*→E6→E8→E7→A8×3→A9→E1 | Four consecutive M2 exchanges; A9 replaces final displaced upper two A tetras |
| A source at 9A, top32 | 9A→32→34→E2 | No-write raw-A entry to split store; top32 construction is not native here |
| B source at BB, original top T | BB→BC→T | Aligned **14**-tetra B store, including service indices37/40 |
| B source at B3, R29=C, original top T | B3→BC→T | Store `(7,B0…B12)` across14 M2 tetras: raw B fields survive one-tetra displaced |

All paths preserve arbitrary physical key pins for the indicated finite
contracts. A1 sets S1=9 and pushes A2; E9 stores without reading old M2 into
the primary state. A7 sets S1=8 and pushes A8. E7 leaves S1=A, and the three
A8 commands increase it C,E,0 before A9 exits. The final displaced page's first
ten A tetras remain, but R30/R33 are replaced by old R32/R35. These are distinct
operations; none establishes a safe native return for an already captured raw
cache or a physical destination page.

`00→32` is not a raw-cache-preserving entry: exact IP00 replaces **all twelve**
A tetras by F, with no ring write. The six raw fields survive iff every one
was already F. This is a ROM IP statement, not a claim about a user program
opcode 00's dispatcher.

For any desired writer entry, the stack-return predecessor words which can
hold all six cache tetras and write nothing are `62,9A,A9,C8`; this is only a
conditional return inventory, not a proof that their target tags are reachable.
The separate completed reset graph audit must decide which source contracts,
selectors, return tags and raw-cache lane are jointly native.

## Reproduction

```sh
/opt/homebrew/bin/python3 tmp/ms-rom-reachability/cache46-writer-audit.py
/opt/homebrew/bin/python3 tmp/ms-rom-reachability/cache46-writer-contracts.py
```

Both pass. Paired overwrite proofs additionally show that 32's lower nine,
34's upper three, E9's twelve and BC's fourteen overwritten M2 tetras have no
surviving copy in the local primary state or its outgoing serial data unless
a backup exists independently before entry.
