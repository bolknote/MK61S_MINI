# memchr: M4 selection and integration

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
use the local body. M0+ native/API sources and its 26-byte SDK fallback remain
unchanged; M0+ hardware selection and complete cross-target integration are
pending. No firmware installation or commit is implied by these source changes.

`tests/run_system_memchr_arm_tests.py` compiles actual native/SDK sources and
checks exact body hashes, read bounds, early hits at unmapped/MPU boundaries,
unsigned search-byte conversion, read-only input, SP and callee-saved registers.
The six linked variants share five distinct code/placement cases: 714,900
functional checks pass. These are emulator checks, never timing results.
Clean F401/F411 release builds and matching System APP/resource gates are
recorded separately from the historical dirty-worktree builds.

Hardware plan SHA-256:
`bb09fece88cfdad86f335bd902349346a806401714f9c201ec94f2136b3453b2`.
Actual strict PASS/restoration receipt SHA-256:
`1a9f3f1e7d1c177ed0fe8c646053a10cd51896f8991848c30baa22a0f36eb8ff`.
The complete raw export in the task's research evidence has manifest SHA-256
`e60dfc3d8b6bad43157ddb09201dd0d9b461e2dd2c65f6a45fb3cc5bc760a3cc`.
