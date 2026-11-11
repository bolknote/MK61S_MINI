# Native LLM M3 integration: physical result, 2026-11-07

The optional third-core backend is implemented in `code/mk61_ai_model.*`,
`ports/picocalc/ai_m3.*`, and the native harness. The default stays RP2.
The same Q4/FP16-scale/LUT_FLOAT32 arithmetic is used on all three cores;
each eight-row tile is split3/3/2. No INT8 activation substitution is made.

Physical firmware: Spectrum shared release47422E0D/C6B786D4, boot4,
RP2040 at125MHz, PERI48MHz, installed STM32 runtime at72MHz. No flash or
clock change was performed by the AI phase. Full model2093896bytes,
SHA256`45ebc482d2247d36d386c9563becb89d3ca08868db66aad001afa977703b0166`.
Native module SHA256`e906ae176ac736e223eb8aca272fa5e3afa88ccc218aee9388f09bbd21c47715`.

| Full forward | RP2 | RP2 + M3 |
|---|---:|---:|
| First token |8.867076s|16.445736s|
| Second token |8.867238s|16.480939s|
| Mean |8.867157s|16.463338s|
| Tokens/s |0.112776|0.060741|

The three-core scheme was1.856665times slower, including all UART traffic.
Both passes used the same kernel, FP32 LUT, prefetch setting and token path.

Actual M3 work:5248jobs,10496rows; each Pico core15744rows. Remote fallback0,
UART errors0, backend error0, unload failures0, maximum native call303µs.
Pico client context1512bytes; STM32 code+BSS4580/6144bytes; Pico DMA use0.
Module setup43.717ms was outside forward timing. Across two target forwards:

- Activation preparation:1.133494s.
- Weight submission/start:11.220099s.
- Join/status/output retrieval:4.763550s.
- UART sent1546911bytes, received622768bytes,22648requests.

Tokens `[292,280]`, complete linear-row hashes `462b7a7b`/`d32364d9`, and
complete KV allocation checksum `03d5c6b5` matched. HOST tests additionally
compare full logits and KV bytes, including prefetch/refusal/fallback/cancel.
This establishes arithmetic parity for this experiment, not language quality.

## Overall hardware result: HOLD

The diagnostic did **not** pass: it recorded289I²C errors during the target
window. Fresh C5 observations later showed I2C_TIMEOUTS4925→4935 over an idle
second, I2C_ABORTS0, and KBD offline. The fault persisted after model execution
and after the native M3 module had been unloaded and EMPTY verified. It is not
an active UART framing error and is not repaired by accepting a new baseline.
Other recorded error counters stayed0, clocks125/48MHz and boot4 unchanged,
calculator/settings/RTC writes0, APP buffers0, firmware CRC valid.

The original measurement receipt remains HOLD. No inference was replayed,
no reset was performed, and no old device state was saved/restored. Guarded
cleanup returned native CLOSED/NONE and removed the original two private
diagnostic directories; their absence was independently checked afterwards.

First read-only I²C peek lost its output because DEBUG_WRITE rejects calls
over128bytes; the probe emitted a longer line and ignored the return value.
This was independently reproduced on the exact ARM ELF with the resident
formatter and actual API limit. The corrected probe uses96-byte checked
chunks, saves raw APP output before assertions, and passes HOST ARM execution:
16lines,272read-only peripheral accesses, no bus/clock/reset writes.

The corrected physical peek completed and was cleaned up. All16snapshots
showed GPIO6/SDA high, GPIO7/SCL low, both functionsI²C, controller enabled,
STATUS0x06idle, TX/RX FIFO0, ABRT0, rawTX_EMPTY0x10/interrupt mask0. SCL timing
HC5000/LC7500 matches10kHz. Both sleep-clock masks retained the I²C clock.
Thus SCL was persistently low while the Pico master was idle. This supports a
stuck bus/peer clock-stretch condition; it does not yet identify the cause
inside STM32. The user subsequently performed the manual power cycle. A
postboot read-only audit showed KBD OK and no new I²C errors over one second;
this observation alone did not establish a code fix.

Old AI directories, the first probe and the corrected probe were all verified
removed. Final native CLOSED/NONE, boot4,125/48MHz, buffers0; KBD remainedWAIT,
I2C_TIMEOUTS14685, I2C_ABORTS0, other errors0. CDC closed, worker3234reaped,
shared ROOT lock released. No new hardware actions remain running.

Physical evidence and supervisors are under `.build/mk61ai/m3-linear/`:
`hardware-result/`, `cleanup/result/`, `i2c-peek/result/`, `i2c-peek-v2/result/`.
The FP32 figures above are a diagnostic comparison, not the best RP2 baseline.
Recovered INT8/nibble physical measurements in `clock-sweep-v6/hil` were:
125MHz 2.5095745s/decode token; 250MHz 1.2053895s; 260MHz 1.1554225s;
270MHz 1.114016s. The 280MHz attempt faulted/rebooted; 290MHz was not run.
These are historical measurements on their pinned firmware/model, not new
measurements on the combined resident. Any benefit claim for a future M3 INT8
backend must compare the same arithmetic/layout/model against the best RP2
variant and include UART traffic. The current M3 backend is still FP32.

Exact installed-source ARM regression subsequently reproduced the delayed
READ after the 1000ms peer watchdog resets its selection to IDLE: the original
callback leaves ADDR pending, while the original watchdog ignores IDLE. A new
WRITE while non-IDLE also reproduced the problem. A minimal fix handles both,
requires complete register/payload receipt, and quiesces/rearms after HAL API
refusals. Seven delay cases, incomplete BKL/CFG/RTC writes, rearm IRQ race,
millisecond wrap, FIFO and concurrent UART/native jobs pass in the ARM model.
HAL peripheral side effects are modeled; this is not a captured STM32 register
snapshot proving the exclusive cause of the original physical failure.

The combined I²C + Spectrum START_RESULT11 + power-status0x0F resident was
committed as `c66374002`, independently rebuilt byte-for-byte from its source
archive, then physically written and readback-verified: SHA256
`3b313836c5fa260851c4a8cc6dc4bca8b3c98b7270cc9e484932cd7f268e7282`.
It is26664bytes; only27pages up to0x08006c00 were erased, with settings beyond
0x0800f800 untouched. No GO/reset/options/protection/backup operations occurred.
The user returned DIP1 OFF and power-cycled. Initial C5 reports KBD OK,
I2C_TIMEOUTS0, startup I2C_ABORTS7/QPI_FALLBACKS1, and zero steady error deltas.
Short UART/power/delayed-read physical validation remains pending. Original
LLM A/B receipts remain HOLD; full LLM/audio/OC runs are not admitted yet.
