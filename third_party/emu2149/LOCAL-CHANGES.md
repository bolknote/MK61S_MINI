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

`PSG_calcStereo` advances tone/noise/envelope generators once and mixes
ABC or ACB with two exact integer rate-converter states supplied by the
caller. The mono PSG body and its serialized132-byte ABI remain unchanged.
Outer channels have gain2 and the centre gain1 in each speaker, preserving
the mono level when A/B/C have equal amplitudes. Both AY and YM DAC tables
are selectable. Tests compare every PSG/stereo state against the independent
serial-tick reference, including isolated-channel routing and fast envelopes.

The native SRAM module alone enables `EMU2149_M3_FIXED_RATE`: its CONFIG
validates all clock/rate/quality/phase preconditions before calling the
8/9-tick weighted kernel. No command can change that configuration. The
general library retains the original fallback for other rates and states.

On M3, weighted channel contributions are accumulated once and panned after
the internal ticks, including changing envelopes. For noise periods above
one, masks span the actual LFSR shifts instead of looping over every tick;
out-of-range imported phases retain the serial fallback. The mono output,
both stereo filters and all oscillator/envelope/LFSR states remain exact.
The private M3 build stores the two0..255 DAC tables as bytes; the pointer
width and serialized PSG body do not change. A fully disabled noise mixer
advances only the noise state. At the validated fixed rate, the8/9-tick
phase update uses exact comparisons/additions instead of division. Only
this private build asserts that PSG, DAC table and stereo filter storage
are disjoint; the ordinary library keeps its general entry points.
Stereo uses the validated phase update directly; the silent mono batch
retains the general tick counter. Zero LFSR shifts return without work.

The M3 build handles changing envelopes outside the ordinary weighted
mixer to reduce register spills. It advances the noise counter directly
when the next edge lies beyond the current sample. Imported counter
phases outside their period continue through the original correction.
The module retains filter state in local variables for each sample slice
and uses signed saturation on Cortex-M3. PCM and exported state remain
bit exact, including truncation toward zero at unity PWM gain.

The M3 mixer groups ticks with the same envelope amplitude and multiplies
each channel's masked IIR weights by that amplitude. For noise periods
above one, an in-range counter uses one division and its remainder to
advance through the exact number of edges. Out-of-range phases still
advance one tick at a time until they are in range.
