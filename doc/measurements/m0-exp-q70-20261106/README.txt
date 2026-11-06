RP2040 Q70 exp refinement, 2026-11-06

The runtime adds a bounded integer correction before the existing Q94/CORE-MATH refinement. It accepts a result only when its complete strict enclosure is on one side of the binary64 midpoint. Other cases keep the independent fallback. The new helper is included only for MK61_M0_RP2040_EABI.

summary.json records the exact math-source hashes, tested working image, qualification scope, all remaining losses, and payload hashes. groups.csv contains all 120 groups. records.jsonl.gz contains one self-contained JSON record per group: input_base64 is the complete fixture input and wire_v5_base64 the original output. Both binary bodies have SHA256 fields. The existing tests/m0_sincos_timing.py decoder and tests/m0_mpfr_oracle.py verify them.

BASE and NEXT isolate the Q70 change on the same earlier platform. CURRENT is the selected current-platform working image. RECHECK repeats the small broad-cos loss; LAYOUT_FOCUS is an unselected placement experiment. Earlier records are never replaced by repeats. Across all runs, 12978 returned values match directed MPFR for 1938 unique inputs.

The current heavy-exp groups take 11.720-12.024 microseconds versus 6.082-6.905 for Qfplib. They remain optimization targets, as does broad cos. Ten pow groups are stably faster; the eleventh is approximately equal within the measured paired spread. The general pow final undecided trap remains.

The measured working firmware contains other platform/AI changes which are not part of this math commit. No clean-checkout whole-image reproduction is asserted. Hardware receipts and full source/phase pins remain in the local .build/m0-offline-finish-20261106-001/physical-session-complete bundle.
