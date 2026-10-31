# memchr: M4 and M0+ hardware selections

ClassicF411 at 96 MHz completed the V6 hardware matrix: 4,320 timing rows,
618 raw reports, 659,808 correctness calls and zero failures. Seven rotating
rounds cover code/data in SRAM and Flash, offsets 0–7, standalone/shared SDK,
and actual resident-body/public-table calls. Interrupts stay enabled; these
are warm-cache measurements. The exact original 512 KiB and all original
files, calculator state/IP and the unset ticking RTC were verified restored.

The chosen F411 native body is `balanced64` in Flash, 450 bytes, SHA-256
`bd4502b3460e1d7c13ffdfe257d0106099e36111433ba9b0e1565cc5172de521`.
Aligned absent 4,096-byte SRAM input takes 6,379 cycles, versus 49,198 for the
frozen SDK byte loop and 10,285 for the separately linked SRAM newlib control.
Flash input takes 7,147 cycles. A measured cached shared SDK call adds about
eight cycles. No body wins every input: the local paired loop is slightly
faster on some long scans, while balanced keeps faster first-byte/n=1 paths.

The M4 native and local SDK source now uses the exact measured body. F401
native and the bounded 64-character INPUT compiler use measured `balanced16`,
270 bytes, SHA-256
`e5ce46b95e76623993455cd0ad24c51ca1d4a0e5a1bfcab2fbf7634db3c98a78`,
to fit tight resource limits. There is no F401 hardware timing claim.
Eight-byte pair alignment prevents a speculative second-word read from
crossing a protection boundary before an earlier valid match is inspected.

The production service structure remains 28 bytes and the public table has
26 entries. The optional 27-slot extension measured in the shadow firmware
is a separate future integration. Both normal and shared SDK builds currently
use their local, hardware-selected target body. The M0+ runtime prototype was
measured with both SRAM and Flash providers; its table extension is not shipped.

`tests/run_system_memchr_arm_tests.py` compiles actual native/SDK sources and
checks exact body hashes, read bounds, early hits at unmapped/MPU boundaries,
unsigned search-byte conversion, read-only input, SP and callee-saved registers.
The eight linked variants share five distinct code/placement cases. Selected
M0+ code passes 142,980 actual-source checks; the four M4 cases retain their
previous functional proofs through exact body identity. These are emulator
checks, never timing results.
Clean F401/F411 release builds and matching System APP/resource gates are
recorded separately from the historical dirty-worktree builds.

Hardware plan SHA-256:
`bb09fece88cfdad86f335bd902349346a806401714f9c201ec94f2136b3453b2`.
Actual strict PASS/restoration receipt SHA-256:
`1a9f3f1e7d1c177ed0fe8c646053a10cd51896f8991848c30baa22a0f36eb8ff`.
The complete raw export in the task's research evidence has manifest SHA-256
`e60dfc3d8b6bad43157ddb09201dd0d9b461e2dd2c65f6a45fb3cc5bc760a3cc`.


PicoCalc RP2040 at 125 MHz completed **6,528 timing rows, 936 raw reports and
837,960 correctness calls, zero failures**. Three APPs compare standalone and
shared builds, instructions in SRAM/Flash and inputs in SRAM/Flash; a fourth
full APP campaign measures the native Flash provider. Each APP runs a full
correctness sweep and seven rotated timing rounds. The original 2 MiB Flash,
calculator/program/settings and the elapsed unset RTC were verified returned;
all known temporary files were removed and the process/port closed.

M0+ selects `pair64`, 400 bytes, SHA-256
`85b442239ce66690453b392f9a35045f5d0cf4de35467a57d73aa4beb65a2d97`,
in SRAM for the resident and both SDK modes. This keeps the original alignment
for paired 32-bit loads and uses the M0+ subtract/mask byte test. The native
Flash prototype used the same `balanced64` body as the SRAM provider and was
slightly slower in the measured warm-cache categories. This placement/call-cost
comparison is separate from selecting the APP-measured `pair64` body.
A cached runtime call costs about six extra cycles and public-table dispatch
about eight. Keeping the APP body local avoids that short-call overhead and
supports existing 26-entry hosts.

For aligned SRAM code/data with no match, rounded cycles are:

| Bytes | Old SDK | Newlib | pair64 | balanced64 | fast64 |
|---:|---:|---:|---:|---:|---:|
| 1 | 21 | 36 | 13 | 10 | 10 |
| 8 | 98 | 61 | 57 | 60 | 113 |
| 16 | 186 | 89 | 76 | 79 | 130 |
| 4096 | 45066 | 14371 | 8164 | 8172 | 8242 |

There is no universal fastest body. `pair64` favors aligned medium/long
throughput and costs three more cycles for an absent one-byte span than
`balanced64`. `fast64` has a slightly better unweighted geometric mean over
the finite corpus, but substantial aligned 8–16-byte regressions. A byte loop
wins several very short or early-hit cases. These data are not an application
workload or a claim about cold-cache, whole-product RAM or power acceptance.
M4 retains its independently selected bodies unchanged.

M0+ strict PASS/restoration receipt SHA-256:
`f68a9ac2e74ed6e3cc12cececa187d17a9ccc96d592885fe02519e151e198cec`.
Frozen plan SHA-256:
`8a13247fc3c1e1ffa3ef1bc6889d54fab994a41659d348044dca64fed5ba0968`.


The 2026-10-31 offline archive adds the historical experiment sources and M4
evidence without changing these accepted product selections. Its checksum and
functional checks are recorded in `offline-audit-2026-10-31.json`; the new
`archive-sha256.json` identifies the exported bytes. Historical pending, HOLD
and failed outcomes retain their original status. `selection-m4.json` is the
earlier provisional proposal, not the current product configuration. The M0+
hardware raw export is not part of this archive.

The early `m4-matrix-v1` export is preserved as an unverified historical
snapshot: all 56 entries disagree with its existing checksum manifest.
`INTEGRITY-AUDIT-2026-10-31.json` records those unresolved differences without
changing the old manifest, reports or their original status fields. Frozen local `.build` fixtures are also not
exported, so tests requiring them remain unqualified here. The source runners
are historical tools with pinned builds, paths and ownership checks; this
archive does not authorize device access or reuse of those packets.
