# Local integration

Version and source are pinned in `UPSTREAM`; the MIT license is unmodified.
Register 7's mask retains bits 6/7 for I/O direction/readback. The APP embeds
the public PSG state, selects the AY 16-level DAC table and integer quality
converter, and provides Spectrum port decoding. The library's allocating
constructor/destructor are not used.

When all channel amplitudes are zero, the integer quality converter advances
the same tone counters, noise LFSR, envelope and output filter in a batch.
Audible channels use the original mixer. A differential test compares the
entire PSG state and output against the reference path for 500000 samples,
including register writes, period changes and mute/unmute transitions.

The ultrasonic-tone mute applies only when tone output is enabled. This
preserves amplitude DAC output when both tone and noise are disabled, and
clears a previously audible output when ultrasonic tone becomes muted.
