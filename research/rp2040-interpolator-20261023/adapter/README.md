# Separate APP-only lifecycle adapter

Status: offline implementation and fault tests. **There is no enabled hardware
entry point.** All five required bindings in `bindings.template.json` remain
null. This adapter does not modify the immutable V2 arithmetic packet.

The accepted transport reference is pinned at SHA-256
`bf1f1eabc52233f8b364c4eec56f98f1e442ebe369f97471f396b7bd156a12ae`.
`Accepted` verifies its 18 named components and the transitive frozen Python
pins before imports. `Wire` executes the actual accepted MathPort framing,
32-byte ACK upload, full `fsget` reconstruction and POSIX CRC validation.
The framed subclass retains the accepted exclusive serial lock and frame
decoder, replaces the legacy truncated-tail status reader, and overrides the
receive loop with an always receive-only implementation. The shared pinned
modules are unchanged. Its screen-packet `send` entry point is disabled.
No screen attach, Flash, DFU,
reset, mount or recursive cleanup method is used.

`Lifecycle` implements the real ordering and independent finalizers:

1. Save the first raw exchange and first complete frame before any follow-up;
   reject a bad first frame, even if a later frame is healthy. An additional
   guard rejects a complete RESET header embedded in a previous partial line.
2. Require the exact idle A748 identity and already acknowledged COMMAND mode.
   Capture a fresh complete calculator snapshot before any upload or APP.
   Reg/stk/hout/dump/IP alone are explicitly insufficient.
3. Capture fresh environment and complete ALL-SD anchors, retaining hidden,
   large-file and FAT metadata semantics in the required provider contract.
4. Use only the proven-absent `/INTRP01` namespace. Journal planned bytes and
   hashes before upload, resolve actual canonical filename case and read back
   bytes. Every APP and raw result is pinned/retained before admission.
5. Verify every owned object before point cleanup; keep unknown, partial or
   changed objects. No recursive removal or repair of user data is attempted.
6. Independently attempt original ALL-SD verification, environment restoration,
   complete calculator restoration/readback, final environment/health checks,
   transcript retention and serial close. Host evidence/journal failures cannot
   skip later finalizers. The first failure never becomes PASS after repair.

APP return is a prerequisite for every device finalizer. `Wire` uses the
accepted `ScreenPort.open_text_start` boundary, which is set after pumping any
old terminal tail. A stale prompt received before the open command cannot
prove completion. A prompt embedded in an APP output line is also insufficient.
After a timeout the only recovery operation is a bounded passive receive; it
sends no status query, escape or keepalive. A one-time detached-state check in
adapter V1 was insufficient: an independently injected valid late CAPS packet
set `attached=True`, enabling the inherited loop's next keepalive before the
APP returned. Adapter V2's loop contains no send/write path, even if the actual
pinned decoder changes that flag asynchronously. Raw received bytes, including
binary packets, are retained independently of the terminal text transcript.
If no fresh terminal prompt arrives, no cleanup/readback/restore command is sent
into the APP. The receipt explicitly records pending restoration and required
operator recovery, keeps the original snapshot and owned files, and closes the
port. This HOLD is not successful state restoration. If the APP returns during
the passive wait, independent finalizers run, retaining the original failure.

The missing hardware bindings are concrete, material dependencies:

* A fresh exclusive coordinator lease and fresh post-Cold return/identity anchor.
* A source-proven A748 calculator provider covering register banks, stack/LAST X,
  program, bank map, return stack, input flags, handlers, IP and UI/terminal
  context, with an independently verified readback relation. It must not use
  the legacy partial restoration routine.
* An APP-only complete ALL-SD provider. The accepted `Reader.install` requires
  fresh double Flash backup. This adapter neither overrides that guard nor
  pretends an older backup receipt is a fresh snapshot.
* Complete settings/alarms and RTC-trajectory preservation, including keeping
  the original `RTC_SET` value. An unset RTC must not be silently configured by
  a `date` command. Final verification must be safe after the full calculator
  restore, without changing handlers/mode again.

`test_lifecycle.py` injects wire-level hardware fakes while executing the real
accepted frame/put/get/CRC code and the actual lifecycle/finally/cleanup code.
The fake full-state/ALL-SD/environment providers are explicitly test doubles;
their success is not evidence that these missing A748 routes exist. The fake
APP execution mutates bank map, return stack, flags and handlers while leaving
ordinary visible numeric state intact. This demonstrates why complete state
preservation is required before hardware access.

Fault coverage includes wrong UID, a first bad frame followed by a good one,
a partial first frame, incomplete or stale state, namespace casefold collision,
CRC corruption, APP timeout, invalid/oversized result, unknown/changed owned
files, cleanup failure, changed FAT attributes, ALL-SD verification failure,
environment/full-state restore failure and full-state restore that changes the
environment. Disk-full evidence/journal errors also preserve restoration and
close attempts. Active APP timeout, stale pre-open prompt, late APP return and
an embedded fake prompt are tested separately. All ordinary user bytes remain
read-only in every case.

`test_passive.py` adds three cases using actual accepted open/wait/CAPS decoder
and serial-close methods, the new receive-only loop and OS doubles. Valid split
CAPS packets before a timeout, an initially attached host and a fresh return
after CAPS all produce zero post-open TX. The no-return cases run the actual
lifecycle finally path, keep the original mock snapshot/owned files, record
pending restoration and close both descriptors. Their preflight/filesystem and
preservation providers are explicit fakes. This is not physical restoration.

`provider-contracts.json` lists the required implementation evidence and current
gaps. Its current A748 reference does not grant a future firmware base admission.
After the coordinator accepts the cold-RAM/USB/memory fixes, the exact new
source, ELF, ABI, ownership and loader proofs must be reviewed again. Historical
IP, date, settings and SD counts must never stand in for fresh observations.

Run offline:

```sh
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/adapter/test_lifecycle.py --output .build/rp2040-interpolator-20261023/adapter-tests-NEW
.build/picocalc-apps-arm-venv/bin/python research/rp2040-interpolator-20261023/adapter/test_passive.py --output .build/rp2040-interpolator-20261023/adapter-passive-NEW
python3 research/rp2040-interpolator-20261023/adapter/lifecycle.py --bindings research/rp2040-interpolator-20261023/adapter/bindings.template.json
python3 research/rp2040-interpolator-20261023/adapter/freeze-adapter.py --tests .build/rp2040-interpolator-20261023/adapter-tests-NEW --passive-tests .build/rp2040-interpolator-20261023/adapter-passive-NEW --output .build/rp2040-interpolator-20261023/adapter-packet-NEW
```

The second command exits with status 2 and a HELD report before constructing
or discovering a device. Populating arbitrary JSON entries does not enable a
hardware path: a separately reviewed concrete provider/lease binding and
execution entry point must still be implemented.

The freeze command verifies the exact tested source hashes, accepted transport,
all immutable V2 files and the 27-case report before copying source, contracts
and selected failure evidence. It creates an offline review packet in a new
directory and never overwrites an existing packet or constructs a serial port.
The adapter still pins mathematical V2 as historical context; V2 timed integrity
is HOLD and corrected mathematical V3 is a separate immutable packet. Neither
adapter version supplies a combined V3 hardware binding or any of the five
missing providers.
