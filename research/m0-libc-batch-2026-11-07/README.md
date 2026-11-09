The grouped Cortex-M0+ campaign covers `strlen`, `strcmp`, `strncmp`,
`memcmp`, `strnlen`, `strcpy`, `strncpy` and `strncat`. All 672 matrix jobs
are exported. Production defaults select the measured native/SDK winners;
the final installed-image guard is still pending after transfer to Spectrum.
See [MEASUREMENTS.md](MEASUREMENTS.md) for the role-specific decisions,
regressions, evidence hashes and remaining hardware work.

The six same-place controls are C, byte1/2/4 and word1/2. Four ordinary SDK
APPs cover standalone/shared runtime and SRAM/Flash candidate code. Each
includes the real public SDK and actual resident native controls; the four
existing runtime slots are used directly. A function without a runtime slot
has an explicit N/A mask, rather than a fabricated runtime measurement.

The hardware plan freezes 35,112 effective operand cases, mapped to 60,656
logical cases before timing. It includes all four source alignments, the
selected eight alignment pairs, SRAM/Flash inputs, short strings, ternary and
power-of-two boundaries, early/late mismatches, unsigned bytes, zero counts,
bounded tails, copy padding and concatenation seeds. The separate exhaustive
HOST semantic corpus covers all 16 alignment pairs and all 58 distinct ARM
bodies, AAPCS, exact stores, bounded reads, unmapped zero-count inputs and real
runtime tails. HOST and synthetic clocks are never physical timing evidence.

Each physical row saves all seven raw 1-microsecond intervals for every
active target. No loop-time subtraction is used. `strncat` resets its initial
destination terminator before every repetition, inside the timed loop.
The native clock/IRQ/cache context and timer source are read-only, captured,
qualified and compared. The ELF, image/footer, native bodies, runtime table,
fixture, APP payload and actual relocated addresses are bound independently.

Streaming uses the existing public file services. `FILE_WRITE_SOURCE` first
publishes a 62,464-byte immutable sentinel file with an order-independent,
repeatable callback. Later, outside timed code, `FILE_BYTES_WRITE` overwrites
at most 4096 bytes at a time. Each raw page and the global header have separate
CRCs, job/nonce correlation and completeness counts. A first fault preserves
earlier pages and its partial page, stops, and is never replayed.

The original executor plan used the existing qualified CDC/ROM gate and supervisor.
It requires one fresh Root campaign Go, exact source/artifact pins, an existing
coordinator lease and a complete fixed Flash reserve audit. It defined
45 bounded phases: fixture installation, four timer/APP qualifications, all
672 grouped timing jobs and release. No old firmware/state/RTC is saved or
restored; no RTC setter, clock change or explicit error clearing exists.

Per-function decisions use the frozen inverse-(length+1) workload with
equal case weight inside a length, with equal-length and inverse-work
sensitivity and full short/long regression maps. Different contexts remain
separate. A HOST pass or a compact function size is not a hardware winner.
