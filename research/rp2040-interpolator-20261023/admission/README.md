# Quiet-boot INTERP admission — separate draft

This draft narrows the measurement window to a source-proven clean boot with
no unreviewed input or foreign owners. It does not supply arbitrary live-state
backup, an opaque CALCAP snapshot, a new firmware base or a hardware lease.
The accepted combined V3 packet remains unchanged.

`integration-plan.json` maps all five outstanding bindings to concrete APIs,
evidence and implementation tasks. The proposed IP0/zero public registers,
stack/LAST X/105-step program, settings sequence331 and RTC_SET0 checks are
admission constraints. They are not claims about the current device, defaults
to write, or a historical restoration source.

* Lease: issue a new INTERP scope with exact packet/UID/operator and approved
  benchmark/read-only helper actions. The current SD-only scope cannot grant it.
* Post-Cold anchor: requalify the actual repaired source/ELF/ABI/clock/allocator
  and peripheral ownership, then durably capture fresh first status/crash and
  public state. No old boot counter, date, IP or settings may replace this.
* Calculator: use a separate compare-only carrier and read-only observer with
  source-proven quiet hidden defaults and full TX/input/owner history. Reject
  any mismatch; do not call full-state restoration or pretend to have captured
  `FULL_FIELDS`. Raw ring phase/strobes may advance normally.
* SD: consume an independently verified complete post-Cold ALL baseline with
  uninterrupted no-original-write lineage, then verify every original byte and
  metadata at exit. `bind_current_all` is read-only admission, not a hidden
  helper installation. If the baseline/lineage is incomplete, obtain a fresh
  upstream snapshot first. Reuse the guarded reader under a new reviewed scope.
* Environment: compare fresh calibrated RTC trajectory/SET0/settings/alarms/CWD.
  These benchmark APPs neither reset nor set the clock. A mutating SET0 restore
  provider belongs to the upstream cold/recovery phase when its return loses
  the clock; it is not automatically required inside the non-resetting window.

`quiet_guards.py` implements pure predicates over normalized evidence. The
normalizing raw observer, actual authority/source/lease provenance verifier,
exact owned UI-return path, real SD helper lifecycle and fresh-base mapping are
not implemented here. Booleans in a model fixture are not implementation proof.
The default policy has no accepted base and the CLI remains HELD.

`scoped.py` is the new compare-only orchestration draft. It accepts the unchanged
reviewed RX-only `Wire` and V3 decoder through the verified combined binding.
It admits the quiet context before any delivery, admits complete SD before
preparing owned files, checks state after each APP, then independently attempts
owned cleanup, all-original byte verification and semantic/environment comparison.
Initial rejection causes no delivery or follow-up state commands. No-return
allows only passive receive, retains pending work/evidence and closes the port.
There is no device factory, restore-to-zero path or hardware entry point.

The storage/observer hooks are interfaces awaiting real implementation. The
tests use explicit port, normalized observation, authority and delivery/SD
doubles. They exercise the real reviewed Wire wrapper and V3 decoder without
executing the numerical matrix or opening any device. Every result remains
`hardware_GO=false` and `real_preservation_PASS=false`.

```sh
python3 research/rp2040-interpolator-20261023/admission/quiet_guards.py
python3 research/rp2040-interpolator-20261023/admission/test_quiet_guards.py --output .build/rp2040-interpolator-20261023/quiet-guard-tests-NEW
.build/picocalc-apps-arm-venv/bin/python -B research/rp2040-interpolator-20261023/admission/test_scoped.py --guard-fixtures .build/rp2040-interpolator-20261023/quiet-guard-tests-NEW --output .build/rp2040-interpolator-20261023/quiet-scoped-tests-NEW
python3 research/rp2040-interpolator-20261023/admission/seal.py --guard-tests .build/rp2040-interpolator-20261023/quiet-guard-tests-NEW --carrier-tests .build/rp2040-interpolator-20261023/quiet-scoped-tests-NEW --output .build/rp2040-interpolator-20261023/quiet-draft-NEW
```

The first command exits2. The sealed draft is for focused review, not execution.
Upstream code snapshots are references to the observed versions, not authority
to use their old scope or private addresses on a future accepted firmware.
