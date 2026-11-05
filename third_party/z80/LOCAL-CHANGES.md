# Local integration changes

Upstream and pinned revision are recorded in `UPSTREAM`; `LICENSE` is unmodified.

- Port callbacks receive the complete 16-bit Z80 I/O address. Immediate IN/OUT
  use A as the high byte; register/block I/O uses BC. This is needed to select
  individual rows of a ZX Spectrum keyboard.
- `MK61_TARGET_PICOCALC` disables stderr diagnostics for the freestanding APP.
  The unused debug trace function is removed by the linker.
- An optional M1 callback surrounds opcode fetches (including prefixes).
  Disk interfaces use it for immediate and delayed ROM paging. Operand and
  indexed-CB data fetches do not invoke the callback.
- An M1 address range skips the callback when a fetch cannot change the
  selected disk ROM. The callback still surrounds the same fetch if the
  map changes. The notification path is separate from ordinary fetches.
- Optional read/write pointers cover four 16 KiB address windows. A null
  pointer uses the original callback; 16-bit address wrap is preserved.
- Optional 1 KiB page views cover the lower and upper 16 KiB when a direct
  window is absent. Spectrum retains these cache pages across bank switches;
  clean pages trap their first store so only modified pages are written back.
  Reads through page views are outlined to keep the APP within 48 KiB.
- BC/DE/HL and their alternate registers share native 16-bit fields with
  their individual bytes. Both supported hosts and RP2040 are little endian;
  the header rejects other byte orders instead of silently swapping registers.
- The individual flag fields share their native F byte. PUSH/POP AF and
  EX AF,AF' no longer assemble or unpack eight separate booleans. GCC ARM
  and Clang host layouts pass ZEXDOC/ZEXALL with the same cycle totals.
- A 256-byte table supplies result-dependent S/Z/5/3/parity flags. Byte
  arithmetic computes half carry, overflow and carry directly; logic and
  CB shifts write the complete F byte. ZEXDOC/ZEXALL pass unchanged.
- Byte reads, next-byte fetches and R increments are explicitly inlined
  under GCC/Clang. Other helpers retain the size-optimized build settings
  so the complete APP still fits the 48 KiB image limit.
- An optional virtual-cycle deadline enables batched LDIR copies through
  existing direct windows or cached pages. Nonoverlapping blocks use the
  resident memcpy; forward overlap retains Z80 byte-by-byte semantics.
  Self-modifying opcode aliases, cold/clean pages, M1 callbacks and pending
  INT/NMI/EI use normal execution. Spectrum caps batches at frame/IRQ and
  run boundaries and disables them for synchronous audio. R, flags, WZ,
  final-iteration timing and address wrap match individual instructions.

CPU instructions, flags and timings otherwise follow upstream. Timings are
instruction based; memory contention and ULA bus effects are outside this core.
