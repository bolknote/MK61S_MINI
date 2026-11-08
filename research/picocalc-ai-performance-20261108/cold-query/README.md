# Complete cold PicoCalc request

The request is «Синус 22» in DEG. A valid result requires a new boot, no reused KV prefix, all 493 input forwards, 12 emitted tokens, compiled program `0E 0D 02 02 1C 50`, and the actual MK-61 core result `0.3746066`. The original complete run took 1,893,006 ms. Short inference benchmarks do not establish the complete request time.

The release combines commit `59e40583b` (exact FP32 scaling and qualified PSRAM reads), KV gathering, parallel attention, tile 28, filtered output head, and normal-chat profiling. Prompt reuse covers the configured context on later requests. The first cold test must report `reused=0`. Loader transfers remain 1 KiB; input/display service occurs every 8 KiB. Stage checkpoints distinguish loading, allocation and clock changes. Full profile lines are split into the supported 128-byte debug writes and saved to SD.

The latest completed research selection retained SPEC 3M LoRA, natural step 6000, through the subsequent paired course. Its planar MKA SHA is `36e45e648f71e4bbf9a7fad03007067d03e9557d2382ac0b97d7326e0c1f78a0`; the lossless paired representation installed on SD has SHA `2cd7233c1302d70b6bf58ea62db78cc8b164e4397dc00f6dec6adef5424eea48`. No model weights are committed. New unfinished training is excluded. See `model-selection.json`.

Firmware combines the physically qualified 048A0B3E fast inference source with the four resident timing/decoder files from F73B20D0. The F73 source used older AI/PSRAM/linker code; the newer qualified inference implementation is retained. Other changes are the listed AI/clock/profiling changes. Spectrum, M3, STM32 BIOS and SD Spectrum assets are preserved. A build check and linker assertions keep every firmware byte below ROMCACHE at `0x101C0000`. Idle Flash uses divider 4; the existing SRAM transition changes it to 6 before 270 MHz and restores 4 after returning to 125 MHz.

Three earlier physical candidates failed (SDK panic and two watchdog resets before the first forward). A saved 3354BE9C checkpoint confirmed that 270 MHz had been reached; leaving USB deinitialized for the query was removed. The retry uses the same USB lifecycle as the successful fast-inference benchmark, with separate preparation/prompt counters. The first candidate overlapped the ROM cache; that mistake was repaired and the complete ROM payload verified by SHA256 plus all five ROM CRCs. These failures are recorded in `measurement.json`; neither provides a successful cold timing.

The release candidate is described by `release-firmware-manifest.json` and `release-source-pins.json`. Physical results are appended only after the complete keyboard-driven query finishes.

## First complete physical result

Firmware F988EF2A / B99E7E71 completed the identical cold request in **1,256,365 ms (20:56.365)** versus **1,893,006 ms (31:33.006)**: 33.63% less time, 1.507x speedup. Input 493, reused 0, output 12. The saved AIS contains model `MKA-A9980CAA-2160856`, program `0E 0D 02 02 1C 50`; actual core execution stopped with X=0.3746066. The controller then closed its own APP and verified 125 MHz / CLOSED / NONE. See `first-complete/`.

Prefill took 1,121.296 s and decode 47.548 s. Attention accounted for 927.851 s, including 110.292 s of KV reads. This identifies a remaining long-context arithmetic cost. The next candidate applies the already validated exact FP32 multiply/add helpers to attention reductions, preserving order and rounding. The full model, KV, eight SPEC cases and ARM kernels match bit for bit; the compiled ARM attention kernels use 2.33–2.47x fewer instructions for 16-row batches. This is not a device latency result; a fresh complete cold query is required.
