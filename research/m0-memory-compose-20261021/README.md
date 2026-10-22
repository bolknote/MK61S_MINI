# V77 math with both frozen memory candidates (V79)

These private offline builds compose the already qualified V77 math arena
with the peer's frozen SRAM and flash memory implementations. The platform
is still the unaccepted 7AEA549E snapshot. No image has been installed.

The exact V77 math overlay and qualification CMake patch are applied on top
of each source-pinned memory candidate. Other files are preserved and the
complete source fingerprint is checked against each new firmware manifest.

| Memory placement | Composition build | Main static RAM | Heap |
| --- | --- | ---: | ---: |
| SRAM | `b2ed0fcc` | 201,432 B | 27,944 B |
| Flash | `02480920` | 198,856 B | 30,520 B |

Math adds no main RAM relative to either memory candidate. It occupies the
same already reserved 4 KiB scratch region as V77, and adds no tables.
All 274 ordinary math input sections retain their exact V77 addresses.
Allocated code/data in all five numerical object files is byte-identical.
The three owned memory function bodies match the peer's frozen bytes;
runtime slots and EABI aliases resolve to the corresponding implementation.
No libgcc archive member is linked.

Both compositions pass:

- 265,409 actual ARM / directed MPFR RNE cases, with all twelve result
  digests identical to V77.
- The complete 114-group / 116-chunk / 23,091-case instruction matrix:
  112 groups below Qfplib and two equal, with zero owned rounding errors.
- Real ROM CLZ/memset and real linked memcpy execution, byte canaries,
  source preservation, ABI and rejection of ordinary global writes.
- Direct calls to the unmodified 512-bit and 1024-bit pow interval functions:
  20 cases at each precision, identical results and zero rounding errors.
  These calls enter the actual memory routines thousands of times. Observed
  callee frames are 2,656 and 4,832 bytes, excluding caller-owned output.

The instruction tool executes owned symbols from each production ELF and
Qfplib from the pinned original diagnostic ELF, on separate instances of the
same Cortex-M0 emulator. The actual captured ROM executes on both sides;
there are no CLZ/memory models. SIO division remains functionally modeled.
These counts do not measure physical cycles or cache stalls.

The same four explicit cache-model variants were replayed on nine streams
per image. Flash matches actual-ROM V77 throughout. SRAM shows a small
increase only on `tan small_medium_remainder`: word-fill LRU rises from
5.0 to 5.375 modeled misses/call. Other streams, including normal f2d,
the composed exact-exponent pow stream and standalone sqrt, are unchanged.
The models omit IRQs, other-core traffic and caller prefetch.

SRAM retains the memory candidate's 30,000-byte APP capacity failure.
Flash preserves 30,520 heap bytes. This does not select a memory placement:
the peer's physical SRAM/flash comparison still comes first, followed by
math on the final accepted frozen source and immutable restore package.

Full source hashes, object checks, results, models and producer identities
are in `doc/measurements/m0-memory-compose-v79-20261021.json`. Numerical
sources, including M4 math, are unchanged from V77. General pow totality
outside the exact stage's 224 exponents remains unproved; the undecided trap
is retained. No hardware speed-parity claim is made here.
