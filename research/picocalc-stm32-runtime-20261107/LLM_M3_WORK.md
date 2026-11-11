# LLM M3 integration

User requested working third-core integration and full-model measurements.
Default remains two RP2040 cores, Q4 weights, LUT_FLOAT32 arithmetic, FP32 KV.
The optional backend reserves up to two tail rows of each eight-row tile for
the STM32, stages one vector per linear, joins every job before consuming or
recycling output, and recomputes failed remote rows locally. Diagnostic PASS
requires actual remote work with zero fallbacks, identical row hashes/tokens,
and includes all activation/weight/result UART traffic in forward timing.

New native module keeps at most 512 binary32 activations and one 32-column
LUT, computes one group per cooperative step, and preserves the RP addition
order. Module loading is outside forward, with separate setup/resource data.
Only claim UART if audio is inactive, pins/UART are free and HELLO is EMPTY;
never UNLOAD another client's module. UART uses no Pico DMA channels.

Hardware access is exclusively coordinated with ROOT/Spectrum. During the
Spectrum window only source edits, compilation and HOST/ARM tests are allowed.
No stored calculator state or old firmware is saved/restored. STM32 resident
firmware is unchanged; this task loads an ordinary native SRAM module.
