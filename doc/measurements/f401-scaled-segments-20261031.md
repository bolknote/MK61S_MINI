# F401 segment planes, 2026-10-31

F401 computes the existing 16x35 segment planes' 10x21 display pixels at compile time. The renderer walks each selected plane's occupied vertical span. It emits 128 bytes of scaled planes instead of the sparse 560-byte source table, and removes runtime coordinate scaling. The original source table and `sourceRow` remain unchanged. F411 and actual Pico preprocessing preserve their previous renderer token stream.

At the unchanged Classic V3 native build flags, BIN shrinks from 259464 to 259016 bytes, saving 448 bytes. Free Flash is 3128 bytes; the required 4096-byte reserve remains short by 968 bytes. The maximum per-function frame stays at 1304/2048 bytes. This source checkpoint is not a qualified release.

A frozen copy of the old 16x35 planes independently verifies all 256 masks over all 256 source-row inputs, including out-of-range rows. Complete 192x64 frames cover all 256 masks in every one of the 12 digit slots and compare against a direct source-pixel oracle. ASAN/UBSAN pass for both legacy and F401 renderers across five physical/USB/lifetime configurations. The complete Pico ASAN/UBSAN suite also passes. The Runner screen oracle and its original source table remain unchanged. No hardware was accessed, and no device timing is claimed.

The adjacent JSON records source pins, preprocessing proofs and test results. The frozen research packet is retained at `.build/f401-runner-size-20261031-001/segment-review-001`.
