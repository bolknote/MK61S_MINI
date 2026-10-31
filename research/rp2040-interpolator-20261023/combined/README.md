# Combined V3 measurement packet

This is the explicit offline join of mathematical packet V3 and RX-only adapter
V2, after both independent focused reviews passed. Their original source,
manifests, APPs, ELF files and review receipts remain byte-identical. The new
binding supplies V3 APP descriptors and the schema3 decoder to the reviewed
`Lifecycle`; it does not call or silently rewrite its historical V2 selector.

`freeze.py` copies both sealed inputs and both complete review artifact chains
into one new directory. The combined manifest also seals this binding, its
focused test evidence, the null provider template and the operator plan. Use
the external SHA in `COMBINED-HANDOFF.json` when opening a frozen packet:

```sh
python3 PACKET/source/bind.py --packet PACKET --manifest-sha SHA_FROM_HANDOFF
python3 PACKET/source/bind.py --packet PACKET --manifest-sha SHA_FROM_HANDOFF --hardware --bindings PACKET/source/bindings.template.json
```

The first command validates the outer manifest, both inner manifests, both
independent review chains and the accepted shared transport dependencies before
importing the reviewed components. It reports the exact four V3 payloads. The
second reports hardware HOLD with exit2 and constructs no port. Arbitrary
populated labels cannot enable a physical execution path.

The operator plan specifies the APP order, 60 raw timing rows, seven ABBA/BAAB
rounds with 4096 calls, exact result sizes/checks, owned namespace and failure
handling. Function, loop, checksum and applicable setup/restore costs stay in
the observations. Empty references are retained without subtraction. No
kernel-only speed or physical cycle claim follows from the offline evidence.

Five real bindings remain absent: an exclusive scoped lease, a fresh post-Cold
anchor on the accepted base, complete calculator preservation through entry
and return, arbitrary-state ALL-SD preservation, and full calibrated RTC/RTC_SET,
settings and alarms preservation. The quiet-boot SD helper and test doubles do
not provide those routes. A748 is the exact offline reference. The future
repaired firmware needs new source/ELF/ABI/loader/allocator/peripheral-ownership
mapping and independent acceptance before a physical transaction can be bound.

For an unreturned APP the reviewed carrier only receives; it sends no query,
escape, ACK or keepalive. The original snapshot and owned files remain, the
receipt says restoration is pending and the port closes. A later healthy
response or successful repair cannot erase the original failure.

`test_binding.py` covers the new join only: all four V3 fixtures; rejection of
V2 schema and wrong variants; a four-APP normal lifecycle and three failure
paths; invalid pins; and null/label-only hardware CLI holds. The actual reviewed
lifecycle and decoder run with explicit wire/provider doubles. The 138625-call
numerical matrix and established transport sweeps are referenced unchanged.

Build a new immutable combined packet after focused tests:

```sh
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/combined/test_binding.py --output .build/rp2040-interpolator-20261023/combined-tests-NEW
python3 research/rp2040-interpolator-20261023/combined/freeze.py --tests .build/rp2040-interpolator-20261023/combined-tests-NEW --output .build/rp2040-interpolator-20261023/combined-v3-NEW
```
