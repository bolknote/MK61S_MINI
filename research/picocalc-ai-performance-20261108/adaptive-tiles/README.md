# Adaptive row batches at270 MHz

Use up to24 rows for128-column matrices and8 for384-column matrices in the
same two weight-tile buffers. Increase the output buffer by64 bytes. Sparse
classifier tiles remain limited to8 rows to preserve the16-span DMA contract.

Two candidate-only passes:0.898694 and0.8931125 s/token, compared with archived
1.114016 and previous1.0720915. No reference was rerun. Worker jobs per pass
fell from9472 to3666. Tokens and all-row checksums match. Hardware tests used
the identical frozen Q4 model, INT8 activation scales and2+2 token trajectory.

The controller initially asserted3383 DMA transfers from a simple tile-count
estimate. Actual3220 is valid: non-full tail tiles can have a gap between
weights and scales, and the backend uses the existing synchronous fallback.
The completed report was checked without rerunning inference. Both full row
coverage and numerical checks passed; the controller was corrected to require
actual prefetch usage instead of the inaccurate count prediction.

HOST validation: ASan/UBSan, all arithmetic modes, complete logits and64-position
KV parity, fewer worker jobs, unchanged weight-buffer size, sparse/refused DMA,
cancel/retry, DMA faults, numeric errors, joins, thaw and workspace guards.
Full PicoCalc model/UI tests and the ARMv6-M firmware build passed.
Final device state:125 MHz calculator, CLOSED/NONE, own launcher removed,
CDC/MSC/lease closed. These are short-context timings.
