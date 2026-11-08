# PSRAM read-clock experiment at270MHz

The higher clock has not beaten the established0.606s/token reference. No inference was executed in these hardware trials: they were private-buffer qualification runs before decoding. The production default remains divider461/256 (24.989MHz SCK); the original QPI program is unchanged.

| Trial | Build / CRC | Read divider | Hardware result |
| --- | --- | --- | --- |
| Initial33MHz | C4E0CF46 / A5A7307E |346/256|Invalid qualification: execution/busy callback was not configured before stress.|
| Corrected25MHz |41F73A0E / B61C493F|461/256|PASS:9473 iterations over5000ms, matching CRC, both worker and frozen-display boundaries exercised.|
| Corrected33MHz, original sampling |99C74E63 / B43FBBD7|346/256|FAIL at first block: byte2 expected0x4A, got0x44. The same block reread at125MHz without rewriting was correct, isolating fast-read corruption.|
|33MHz, later PIO sampling |F5A508C5 /89DFA08E|346/256|HOST/ARM checks only; never flashed or qualified on the device.|

The new `--ai-psram-late-read` flag explicitly opts into an experimental program which samples inputs one PIO cycle later, preserving three HIGH and three LOW cycles per SCK, packet duration, write instructions, CE# and FIFO safety. It does not bypass the input synchronizer. The PIO tests compare both programs with finite FIFOs and DMA stalls; they establish digital timing, not electrical reliability. The flagged build gets its own source/build identity and manifest field. It is not the archived F5 image.

The diagnostic now configures execution before stress, reports byte/status/CRC failure details, and restores125MHz before rereading a failed private block without rewriting it. A narrowly restricted AIPERF2 `repeat=0` configuration performs stress without any model forward. The owned stress allocation is64KiB; model and KV storage are excluded. Normal chat, long-context diagnostics, shared activation preparation, gathered/parallel KV reads, quantization, and exact attention arithmetic are retained. No physical KV-parity or new model-quality result is claimed by these receipts.

The archived manifests, raw reports, patches and relevant source pins identify historical candidates. They were built on frozen87321134/E7B6428E including the then accepted Spectrum SRAM changes. Those unrelated working-tree changes are excluded from this commit. Historical `ready.json` files describe preparation at the time, not a current device lease or permission to flash.

Next hardware step: qualify the flagged late-sampling build with the same private-buffer stress before any inference. Only a passing device run permits comparison against0.606s/token.
