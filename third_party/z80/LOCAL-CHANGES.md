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
- One 64-entry table per direction covers all 64 KiB in 1 KiB pages.
  Every CPU byte access uses a single table lookup; a null pointer uses the
  original callback. This also keeps code in partially cached upper banks
  on the inline path. Clean cache pages trap their first store so only
  modified pages are written back. Spectrum rebuilds both tables after
  paging, cache misses and first stores; 16-bit address wrap is preserved.
- Four contiguous 16 KiB views remain available to LDIR batching. They
  describe the same memory as the CPU page tables and allow a batch to
  cross internal page boundaries without another lookup.
- BC/DE/HL and their alternate registers share native 16-bit fields with
  their individual bytes. Both supported hosts and RP2040 are little endian;
  the header rejects other byte orders instead of silently swapping registers.
- The individual flag fields share their native F byte. PUSH/POP AF and
  EX AF,AF' no longer assemble or unpack eight separate booleans. GCC ARM
  and Clang host layouts pass ZEXDOC/ZEXALL with the same cycle totals.
- Live registers and interrupt flags precede callbacks/maps, within
  Thumb-1's short byte/halfword load ranges. The layout is internal;
  Spectrum snapshots still serialize individual Z80 registers.
- A 256-byte table supplies result-dependent S/Z/5/3/parity flags. Byte
  arithmetic computes half carry, overflow and carry directly; logic and
  CB shifts write the complete F byte. ZEXDOC/ZEXALL pass unchanged.
- Byte reads, next-byte fetches and R increments are explicitly inlined
  under GCC/Clang. Other helpers retain the size-optimized build settings
  so the complete APP still fits the 48 KiB image limit.
- A shared dispatcher loops over instruction batches without returning
  through opcode-fetch/step/dispatch stack frames for each instruction.
  Prefix fallback and IM0 enter the same dispatcher for one opcode without
  fetching or processing an extra interrupt. Normal batches still sample
  EI/NMI/INT after every complete instruction and honor stop/HALT boundaries.
- LD and byte ALU groups share the Z80 register-operand decoder. The saved
  code permits GCC `-O2` on the batch dispatcher while the rest of the APP
  retains its size setting (47,856 loaded bytes in the 2026-11-08 build).
- INC/DEC use result-indexed flag tables; 16-bit ADD computes H/C directly
  and preserves S/Z/PV; EXX swaps native register pairs. Exhaustive byte/F
  tests, 786,432 word-add cases, and both full ZEXDOC/ZEXALL runs retain the
  expected flags and 46,734,978,649 t-states per exerciser.
- An optional virtual-cycle deadline enables batched LDIR copies through
  existing direct windows or cached pages. Nonoverlapping blocks use the
  resident memcpy; forward overlap retains Z80 byte-by-byte semantics.
  Self-modifying opcode aliases, cold/clean pages, M1 callbacks and pending
  INT/NMI/EI use normal execution. Spectrum caps batches at frame/IRQ and
  run boundaries and disables them for synchronous audio. R, flags, WZ,
  final-iteration timing and address wrap match individual instructions.

CPU instructions, flags and timings otherwise follow upstream. Timings are
instruction based; memory contention and ULA bus effects are outside this core.
