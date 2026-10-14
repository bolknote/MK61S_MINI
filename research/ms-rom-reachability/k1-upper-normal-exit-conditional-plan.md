# Conditional normal-exit allocation after NOP → RCL0

This is a symbolic composition of previously tested block contracts, **not a
new native result**. No new emulator runs were made for this note. The necessary
safe removal of the V marker has not been found.

The parent investigation's native starting layout is:

```text
ordinary P0=w; X1=INV0; X/Y/Z/T=w/1/u/q
Ms U/V/W/Q=v/m/a/p; upper P7/P8/P9/P10=w/b/c/d
```

Here `m` is the remaining V marker. `q` exists only in visible T; `u` only in
visible Z; `p` only in Q; `a` only in W. `w` already has a stored upper copy.

## The missing operation

The allocation below requires a **hypothetical**, safe transition to normal
marker geometry with `V=w` and everything else unchanged. This prerequisite is
not achieved by ordinary K×. The parent's fresh native K× test with lead phase 0
instead changed Q from `p` to `w` and the control word to the `28h` family, losing
the only copy of `p`. With just the real and V markers, the ordinary E9 route
targets X1 or Q, not V. The former successful K× cleanup had a T marker; RCL0
has removed that marker in the present state. Those older results do not transfer.

## Allocation if the missing operation were obtained

`Fcomma` denotes ordinary `F ,`. This table assumes clean normal marker/control
entry throughout; it must not be applied directly to the actual V-marked state.
`r` is the ordinary P9 value, which remains stored normally.

| Operation | X/Y/Z/T | P0 | U/V/W | Q | Upper |
| --- | --- | --- | --- | --- | --- |
| Hypothetical safe V cleanup | w/1/u/q | w | v/w/a | p | w/b/c/d |
| Fcomma × 3 | q/w/1/u | w | v/w/a | p | w/b/c/d |
| STORE0 q | q/w/1/u | q | v/w/a | p | w/b/c/d |
| Fcomma × 3 | u/q/w/1 | q | v/w/a | p | w/b/c/d |
| `stack.read` | a/0/u/q | q | v/w/a | p | w/b/c/d |
| STORE0 a | a/0/u/q | a | v/w/a | p | w/b/c/d |
| `stack.push` | 0/u/r/r | a | q/v/w | p | w/b/c/d |
| Fcomma × 2 | r/r/0/u | a | q/v/w | p | w/b/c/d |
| `stack.push` | r/0/r/r | a | u/q/v | p | w/b/c/d |

The read contract from `k1-visible-q-swap-check.cjs` is
`X=t,P0=h,W=C → X/Y/Z/T=C/0/t/h`, with all stored words restored. This is why
STORE0 a is safe **after** read: q has been placed in T. The standalone push
contract is `x/y/z/t; U/V/W=A/B/C → y/z/r/r; U/V/W=t/A/B`; its old W must have
a backup. In the first push a is backed up in P0; in the second w is backed up
in upper P7. `stack.finish` and the older P0-hub lower-cycle are not substitutes
for this read contract.

The conditional endpoint stores all 23 originals. Relative to the original
baseline its moved values are P0←a, Q←p, V←q, W←v, P7←w; U is restored to u.
The corresponding source-to-destination cycle is `(P0 Q V W P7)`.
Even with a future safe V cleanup, the full keyboard composition and its input
domain would still require native verification.

## Existing AD → A3 evidence is not a ready exit

`k1-origin-secondary-selection.md` proves a local AD → A3 fragment without E9
for a precondition including R35=3. A3 writes three header tetras in the next
physical page. Its examined AD-at-W placement therefore still overwrites Q,
which is unsafe here because Q holds the only p. That proof does not supply a
keyboard-reachable safe native entry or an exit.

`check_keyboard_decode.py` proves that ordinary 9F enters AA only when the
pending opcode's high nibble is at least 4. Consequently a plain Fcomma (25h)
does not itself provide an ordinary AA → AD → A3 shortcut. This is a limitation
of that direct entry family, **not** a global impossibility proof for AD → A3.

No already-tested native AD → A3-without-E9 exit suitable for the current layout
was identified in the reviewed contracts.
