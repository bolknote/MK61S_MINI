# Qualified AI placement:0.717 seconds/token

The previous installed5CC4EF8E image measured0.770563/0.771089 s/token after
cold diagnostics and unrelated UI growth shifted flash code. The earlier
E0CDF5AB image had measured0.7291845/0.7292815. This change preserves all four
AI fixes and restores the model's measured cache-index layout.

`mk61_ai_model.cpp.o` instruction sections now execute from a dedicated flash
slot at0x101ac248. The forward entry is0x101ae828, and its two linear/load
lambdas retain offsets0x2b0/0x914 in the8KiB XIP index period, matching E0CDF5AB.
The SDK text and RAM catch-alls exclude only these instruction sections;
model read-only data retains its ordinary flash placement. No inference or
quantization arithmetic changes and no new SRAM code allocation are involved.
Cold long-context diagnostics remain in their separate flash slot.

BuildBA33A5D4/574C304F,270 MHz, two M0+ cores, INT8,28-row tiles, DMA prefetch,
full classifier and the same pinned model MKA-AA8246E1-2093896 measured:

| Pass | Seconds/token | Presentation microseconds/token |
|---:|---:|---:|
|1|0.7172665|172.0|
|2|0.7176080|165.5|

The old firmware was not rerun. Both passes matched all archived tokens and
whole-linear-output checksums. No freeze violations or I2C errors occurred.
The matching model SHA256 is in receipt.json. Tests include native UI lifecycle
with ASan/UBSan and all eight published real-model Russian SPEC fixtures in
INT8, matching exact tokens, compiled programs and MK61 emulator outputs.

All four features remain: ordinary-chat INT8/270 MHz with restoration; the
64/128/256 long-context diagnostic with selected same-MCU verification;
activation preparation reuse (71→41 per full decode); shared GQA KV reads.
The previous long-context results are recorded in ../chat-context/. They were
not rerun because this change relocates unchanged instructions only.

The source was frozen from main170fc9514 plus the qualified AI changes;
uncommitted Spectrum/audio WIP was excluded as the coordinator requested.
Spectrum data, STM32 BIOS and the root model were not changed. The image uses
1770112 flash bytes and119816 static SRAM bytes, with109560 heap bytes.
After measurement, temporary APPs were removed, clocks restored to125 MHz,
and CDC/MSC/board lease were closed. The installed candidate is the winner.
