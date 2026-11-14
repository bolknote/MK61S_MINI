# Stereo/PWM diagnostic after the reported silence

The user reports no audible sound. Existing Spectrum rate/event counters do not
prove speaker output. No STM32 audio firmware/offload has been implemented.

HOST replay of the frozen Cosmic trajectory (fixed P at frames100..199;
not identical to physical HIL input) produces nonzero PCM in each of the ten
complete300-frame windows. Across those windows PCM is -6534..11998. Using the
actual native gain formula at master10, PWM differs from128 in55..78% of samples.
Master0 produces128/128 despite successful SYNTH_OPEN and running callbacks.
Actual device master volume is unknown. Zero-volume mute is a hypothesis.

SPAUDCHK uses only the existing native25000Hz AUDIO_SYNTH API, PCM +/-16384,
requested volume100. It reads the current master setting once and never writes
settings. Sequence:2s silence,2s left500Hz,2s right1000Hz,2s both,.5s silence.
It waits for212500 callbacks or a12s timer deadline. It calls CLOSE before its
stack context expires. At master10 native PWM must range96..160; at master0
all phases remain128/128 and the report explicitly says mute=1. A valid muted
diagnostic remains operationally valid and does not claim audible output.

During the sequence core0 reads only PWM5_CSR/CC and GPIO26/27_CTRL. Addresses
and pin function4 are checked against the local RP2040 Pico SDK and installed
native audio source. Phase extrema are sampled away from boundaries. Audio API
does all PWM/timer writes. CSR is checked enabled before close and disabled
after close. No direct MMIO writes, heap allocation, PSRAM, firmware or ABI change.

HOST verification: actual APP executes five ASan/UBSan fake-native scenarios:
master10 normal and wrapping clock, master0, disabled PWM, stalled callbacks.
It verifies signed stereo/PWM, phase order, one close, quiescent callback context,
and one read-only settings getter. Seven Python controller tests exercise report
validation for every master0..10, invalid/missing/duplicate phases and lifecycle,
immutable scope before device I/O, foreign/running foreground refusal, one-temp
cleanup, failure release, and no ordinary APP/oldstate/settings operations.

APP1387bytes, SRAM1544bytes. This is a dedicated signal probe, not a performance
candidate. Callback/PWM evidence cannot prove amplifier/speaker audibility. Ask
the user whether both tones were heard when the approved hardware run occurs.

Controller requires fresh released supplier receipt, strict native2483/22F8ED32
at125MHz/physicalkeys0, unchanged UID USB binding, closed descriptors/noerrors,
noholders and reaped0 supervisor. Only SPAUDCHK.APP may be uploaded, opened once,
automatically exited and deleted. Occupied diagnostic filename or insufficient
contiguous heap causes HOLD before upload. It never resets or changes firmware.
One90s phase and45s cleanup, maximum135s total plus150s external supervisor/reap;
marker wait20s. First fault HOLD with no replay. Cleanup keys target only its
finished own viewer/browser, never another APP or a still-running diagnostic.
The ordinary SPECTRUM.APP is not read or changed; old state and RTC are not read,
backed up, analyzed or restored. Native/descriptor/holder proofs follow cleanup.

Current packet is a HOST draft based on the last completed Spectrum release.
PicoCalc belongs to Harness. No diagnostic execution is authorized by this draft;
after Harness release the current native supplier/binding must replace it and
Root must issue an exact new phase GO. Firmware changes require a new review.
