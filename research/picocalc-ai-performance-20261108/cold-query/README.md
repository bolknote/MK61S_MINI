# Complete cold PicoCalc request

The request is «Синус 22» in DEG. A valid result requires a new boot, no reused KV prefix, all 493 input forwards, 12 emitted tokens, compiled program `0E 0D 02 02 1C 50`, and the actual MK-61 core result `0.3746066`. The original complete run took 1,893,006 ms. Short inference benchmarks do not establish the complete request time.

The release combines commit `59e40583b` (exact FP32 scaling and qualified PSRAM reads), KV gathering, parallel attention, tile 28, filtered output head, and normal-chat profiling. Prompt reuse covers the configured context on later requests. The first cold test must report `reused=0`. Loader transfers remain 1 KiB; input/display service occurs every 8 KiB. Stage checkpoints distinguish loading, allocation and clock changes. Full profile lines are split into the supported 128-byte debug writes and saved to SD.

The latest completed research selection retained SPEC 3M LoRA, natural step 6000, through the subsequent paired course. Its planar MKA SHA is `36e45e648f71e4bbf9a7fad03007067d03e9557d2382ac0b97d7326e0c1f78a0`; the lossless paired representation installed on SD has SHA `2cd7233c1302d70b6bf58ea62db78cc8b164e4397dc00f6dec6adef5424eea48`. No model weights are committed. New unfinished training is excluded. See `model-selection.json`.

Firmware comes from the frozen, physically qualified 048A0B3E platform source with only the listed AI/clock/profiling changes. Spectrum, M3, STM32 BIOS and SD Spectrum assets are preserved. A build check and linker assertions keep every firmware byte below ROMCACHE at `0x101C0000`. Idle Flash uses divider 4; the existing SRAM transition changes it to 6 before 270 MHz and restores 4 after returning to 125 MHz.

Two earlier physical candidates failed (SDK panic and watchdog during loading). The first candidate overlapped the ROM cache; that mistake was repaired and the complete ROM payload verified by SHA256 plus all five ROM CRCs. These failures are recorded in `measurement.json`; neither provides a successful cold timing.

The release candidate is described by `release-firmware-manifest.json` and `release-source-pins.json`. Physical results are appended only after the complete keyboard-driven query finishes.
