# Actual RP2040 ROM qualification (V78)

Earlier math instruction profiles modeled SDK CLZ, memcpy and memset calls.
The optional `--bootrom` mode now loads the captured 16 KiB ROM at address
zero and executes the SDK's bit/memory lookup initializers. The wrappers
and ROM bodies then execute as ARM instructions; no intrinsic is replaced
by a host operation. Only writes to the initializer's exact pointer table
are temporarily allowed. Ordinary calls retain the stack/SIO write guard.

The dump is ROM V3 from Pico H `E6657CD423721C35`, captured twice identically.
Its SHA256 is `ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe`.
This changes the test harness, not firmware, ROM contents or math code.

On the exact qualified V77 production and diagnostic images:

- All 265,409 directed MPFR RNE checks pass; all twelve result digests match
  the earlier modeled run.
- The complete 114-group / 116-chunk / 23,091-case instruction matrix still
  has 112 groups below Qfplib and two equal, with no owned rounding error.
- Actual ROM execution adds 0.234375 instructions/call to `tan small_reduced`
  and 1.171875 to `tan small_medium_remainder`. Other group means are unchanged.
- 256 CLZ inputs, 704 memcpy cases and 704 memset cases verify real code,
  alignment, byte canaries, source preservation and ABI. An ordinary call
  attempting to overwrite the pointer table is rejected by the write guard.

The Qfplib source remains the pinned original. Both sides run in the same
diagnostic ELF. Instruction counts do not include bus stalls, IRQs or the
other core, and SIO division is still functionally modeled. Hardware speed
parity remains unverified.

Run `tests/qualify_m0_rounding.py` with `--elf`, `--bootrom` and `--json`.
Run `tests/profile_m0_math_matrix.py` with `--benchmark`, `--bootrom`,
`--baseline` (optional) and `--json`. The primitive/guard check is
`tests/m0_rom_intrinsics_arm_self_test.py`, with `--elf`, `--bootrom` and
`--json`. Use the captured ROM under
`research/rp2040-memset-2026-10-21/capture/bootrom.bin`.

The full results and identities are in
`doc/measurements/m0-real-rom-v78-20261021.json`. V77 remains a private
prototype on an unaccepted platform. General pow totality outside its
exact stage's 224 exponents remains open; the undecided trap is retained.
